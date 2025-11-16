from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from .models import (
    PurchaseOrder, SKU, QCForm, SparePartRequest, 
    TechnicianAnalytics, MovementRequest, PurchasingNotification, SparePartInventory, StockAdjustment, ReturnedPart, InstallationPhoto, SalesOrder, Payment
)
from django.urls import reverse_lazy
from django.views import generic
from .forms import CustomUserCreationForm, PurchaseOrderForm, PORejectionForm, SparePartInventoryForm, StockAdjustmentForm, StockAdjustmentRejectForm, SalesOrderForm, PaymentForm, ShippingFileForm
from django.contrib import messages
from django.db.models import Count, Q, Sum 
from django.utils import timezone
from django.http import JsonResponse
from django.template.loader import render_to_string

# --- Cek Role ---
def is_warehouse_manager(user):
    return user.groups.filter(name='Warehouse Manager').exists()
def is_technician(user):
    return user.groups.filter(name='Technician').exists()
def is_lead_technician(user):
    return user.groups.filter(name='Lead Technician').exists()
def is_purchasing(user):
    return user.groups.filter(name='Purchasing').exists()
def is_sales(user): 
    return user.groups.filter(name='Sales').exists()

@login_required(login_url='login') 
def dashboard(request):
    user = request.user 

    # Data Umum Sidebar (untuk semua role kecuali Teknisi)
    skus_under_tech = SKU.objects.filter(
        assigned_technician__isnull=False
    ).select_related('assigned_technician').order_by('assigned_technician__username')
    sidebar_context = {
        'sidebar_skus_under_tech': skus_under_tech,
    }
    ready_skus_list = SKU.objects.filter(status='Ready').order_by('name')
    shop_skus_list = SKU.objects.filter(status='Shop').order_by('name')
    
    # Kumpulkan dalam satu konteks
    ready_list_context = {
        'ready_skus_list': ready_skus_list,
        'shop_skus_list': shop_skus_list
    }
    if is_warehouse_manager(user):
        pending_part_requests = SparePartRequest.objects.filter(status='Pending')
        skus_need_shelving = SKU.objects.filter(
            status='Ready', 
            shelf_location__isnull=True 
        )
        # Notifikasi PO yang perlu di-approve
        pending_po_approvals = PurchaseOrder.objects.filter(status='Pending_Approval').count()
        
        context = {
            'pending_parts': pending_part_requests,
            'skus_need_shelving': skus_need_shelving,
            'pending_po_approvals': pending_po_approvals 
        }
        context.update(sidebar_context) 
        context.update(ready_list_context)
        return render(request, 'app/dashboards/wm_dashboard.html', context)

    elif is_technician(user):
        my_assigned_skus_current = SKU.objects.filter(
            assigned_technician=user, 
            status='QC'
        )
        my_skus_to_install = SKU.objects.filter(
            assigned_technician=user,
            status='AWAITING_INSTALL'
        )

        my_assigned_skus_history = SKU.objects.filter(
            assigned_technician=user
        ).exclude(
            status__in=['QC', 'QC_PENDING', 'AWAITING_INSTALL'] 
        ).order_by('-id')
        
        context = { 
            'my_skus': my_assigned_skus_current,
            'my_skus_to_install': my_skus_to_install, 
            'my_skus_history': my_assigned_skus_history
        }
        # Teknisi tidak perlu sidebar umum
        return render(request, 'app/dashboards/tech_dashboard.html', context)

    elif is_lead_technician(user):
        pending_qc_forms = QCForm.objects.filter(
            sku__status='QC_PENDING'
        ).select_related('sku', 'technician')
        pending_final_checks = QCForm.objects.filter(
            sku__status='PENDING_FINAL_CHECK',
            installation_submitted_at__isnull=False, # Pastikan teknisi sudah submit
            final_approval_at__isnull=True # Pastikan belum di-approve
        ).select_related('sku', 'technician')
        parts_awaiting_receipt_approval = SparePartRequest.objects.filter(
            status='PENDING_LEAD_RECEIPT'
        ).select_related('qc_form__sku', 'qc_form__technician')
        context = { 
            'pending_forms': pending_qc_forms,
            'pending_final_checks': pending_final_checks,
            'parts_awaiting_receipt_approval': parts_awaiting_receipt_approval 
        }
        context.update(sidebar_context)
        return render(request, 'app/dashboards/lead_dashboard.html', context)

    elif is_purchasing(user):
        parts_to_buy = SparePartRequest.objects.filter(status='Approved_Buy')
        po_notifications = PurchasingNotification.objects.filter(is_resolved=False)
        # Notifikasi PO yang ditolak WM
        rejected_pos = PurchaseOrder.objects.filter(status='Rejected')
        pending_adjustments = StockAdjustment.objects.filter(
            status='Pending'
        ).select_related('spare_part', 'requested_by')

        context = {
            'parts_to_buy': parts_to_buy,
            'po_notifications': po_notifications,
            'rejected_pos': rejected_pos,
            'pending_adjustments': pending_adjustments
        }
        context.update(sidebar_context) 
        context.update(ready_list_context)
        return render(request, 'app/dashboards/purchasing_dashboard.html', context)
    elif is_sales(user):
        # Ambil semua order yang dibuat oleh sales ini
        my_orders = SalesOrder.objects.filter(
            sales_person=user
        ).select_related('sku').prefetch_related('payments').order_by('-created_at')

        # Form untuk '+ Add Customer'
        form = SalesOrderForm()

        context = {
            'my_orders': my_orders,
            'add_order_form': form,
        }
        # Sales juga bisa melihat list SKU Ready dan Ready Store
        context.update(sidebar_context) 
        context.update(ready_list_context) 
        return render(request, 'app/dashboards/sales_dashboard.html', context)

    # Fallback jika tidak punya role
    return render(request, 'app/dashboard.html')

@login_required(login_url='login')
@user_passes_test(is_sales)
def sales_order_add(request):
    """View untuk memproses form '+ Add Customer'."""
    if request.method == 'POST':
        form = SalesOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.sales_person = request.user
            order.status = 'Pending' # Status awal, belum ada pembayaran
            order.save()
            
            # PENTING: Saat order dibuat, SKU *belum* berubah status.
            # Status SKU baru berubah saat pembayaran pertama masuk.
            
            messages.success(request, f"Order untuk {order.customer_name} berhasil dibuat. Silakan tambahkan pembayaran pertama.")
            return redirect('sales_order_detail', order_id=order.id)
        else:
            # Jika form tidak valid, kembali ke dashboard dan tampilkan error
            # Kita perlu re-fetch data dashboard
            my_orders = SalesOrder.objects.filter(sales_person=request.user).select_related('sku').prefetch_related('payments').order_by('-created_at')
            
            # Ambil data sidebar lagi
            skus_under_tech = SKU.objects.filter(assigned_technician__isnull=False).select_related('assigned_technician').order_by('assigned_technician__username')
            ready_skus_list = SKU.objects.filter(status='Ready').order_by('name')
            shop_skus_list = SKU.objects.filter(status='Shop').order_by('name')

            context = {
                'my_orders': my_orders,
                'add_order_form': form, # Kirim form yang tidak valid agar error terlihat
                'sidebar_skus_under_tech': skus_under_tech,
                'ready_skus_list': ready_skus_list,
                'shop_skus_list': shop_skus_list
            }
            messages.error(request, "Gagal menambahkan order. Cek error di bawah form.")
            return render(request, 'app/dashboards/sales_dashboard.html', context)
            
    return redirect('dashboard') # Jika bukan POST, kembalikan ke dashboard

@login_required(login_url='login')
@user_passes_test(is_sales)
def sales_order_detail(request, order_id):
    """Menampilkan detail satu order (card) dan form untuk menambah pembayaran."""
    order = get_object_or_404(SalesOrder, id=order_id, sales_person=request.user)
    payments = order.payments.all().order_by('-payment_date')
    
    payment_form = PaymentForm()
    shipping_form = ShippingFileForm(instance=order) # Form untuk upload resi/bukti terima
    
    context = {
        'order': order,
        'payments': payments,
        'payment_form': payment_form,
        'shipping_form': shipping_form,
        'total_paid': order.get_total_paid(),
        'remaining_balance': order.get_remaining_balance()
    }
    return render(request, 'app/sales_order_detail.html', context)

@login_required(login_url='login')
@user_passes_test(is_sales)
def add_payment(request, order_id):
    """Memproses penambahan pembayaran."""
    order = get_object_or_404(SalesOrder, id=order_id, sales_person=request.user)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.sales_order = order
            payment.save()
            
            # Panggil fungsi untuk update status SKU
            order.update_status_based_on_payment()
            
            messages.success(request, f"Pembayaran sebesar {payment.amount} berhasil ditambahkan.")
        else:
            messages.error(request, "Gagal menambah pembayaran. Pastikan file bukti transfer diupload.")
            
    return redirect('sales_order_detail', order_id=order.id)

@login_required(login_url='login')
@user_passes_test(is_sales)
def upload_shipping_files(request, order_id):
    order = get_object_or_404(SalesOrder, id=order_id, sales_person=request.user)
    
    if request.method == 'POST':
        form = ShippingFileForm(request.POST, request.FILES, instance=order)
        if form.is_valid():
            if 'shipping_receipt' in form.changed_data:
                order.shipped_at = timezone.now()
                order.status = 'Shipped'
            
            if 'proof_of_receipt' in form.changed_data:
                order.completed_at = timezone.now()
                order.status = 'Completed'

            form.save() 

            messages.success(request, "File pengiriman berhasil di-update.")
        else:
            messages.error(request, "Gagal meng-update file pengiriman.")
            
    return redirect('sales_order_detail', order_id=order.id)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def inventory_dashboard(request):
    inventory_list_manual = SparePartInventory.objects.filter(
        Q(origin='MANUAL') | Q(origin='PURCHASE')
    ).order_by('part_name')
    
    # Ambil part hasil pengembalian (RETURN)
    inventory_list_returned = SparePartInventory.objects.filter(
        origin='RETURN'
    ).order_by('part_name')

    context = {
        'inventory_list_manual': inventory_list_manual,
        'inventory_list_returned': inventory_list_returned
    }
    return render(request, 'app/dashboards/wh_inventory_dashboard.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def inventory_add(request):
    if request.method == 'POST':
        form = SparePartInventoryForm(request.POST)
        if form.is_valid():
            part = form.save(commit=False)
            part.origin = 'MANUAL'
            if part.quantity_in_stock > 0:
                part.status = 'Ready'
            else:
                part.status = 'Out_Of_Stock'
            part.save()
            messages.success(request, f"Spare part '{form.cleaned_data['part_name']}' berhasil ditambahkan ke inventory.")
            return redirect('inventory_dashboard')
    else:
        form = SparePartInventoryForm()
        
    context = {
        'form': form,
        'form_title': 'Tambah Spare Part Baru'
    }
    return render(request, 'app/inventory_form.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def inventory_adjust(request, part_id):
    part = get_object_or_404(SparePartInventory, id=part_id)

    # Cek apakah sudah ada penyesuaian yang pending
    if part.has_pending_adjustment():
        messages.error(request, f"Sudah ada penyesuaian yang pending untuk '{part.part_name}'. Harap tunggu approval Purchasing.")
        return redirect('inventory_dashboard')

    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            adj = form.save(commit=False)
            adj.spare_part = part
            adj.requested_by = request.user
            adj.quantity_in_system = part.quantity_in_stock # Catat stok lama
            adj.status = 'Pending'
            adj.save()
            
            # "Kunci" item inventory
            part.status = 'Pending_Adjustment'
            part.save()
            
            messages.success(request, f"Permintaan penyesuaian stok for '{part.part_name}' telah dikirim ke Purchasing.")
            return redirect('inventory_dashboard')
    else:
        form = StockAdjustmentForm()

    context = {
        'form': form,
        'part': part,
        'form_title': f'Adjust Stok: {part.part_name}'
    }
    return render(request, 'app/inventory_adjust.html', context)

@login_required(login_url='login')
@user_passes_test(is_purchasing)
def approve_stock_adjustment(request, adj_id):
    adjustment = get_object_or_404(StockAdjustment.objects.select_related('spare_part', 'requested_by'), id=adj_id, status='Pending')
    part = adjustment.spare_part
    reject_form = StockAdjustmentRejectForm()

    if request.method == 'POST':
        if 'approve' in request.POST:
            # 1. Update Inventory
            part.quantity_in_stock = adjustment.quantity_actual
            # Tentukan status baru berdasarkan stok baru
            if part.quantity_in_stock > 0:
                part.status = 'Ready'
            else:
                part.status = 'Out_Of_Stock'
            part.save()
            
            # 2. Update Adjustment Request
            adjustment.status = 'Approved'
            adjustment.managed_by = request.user
            adjustment.managed_at = timezone.now()
            adjustment.save()
            
            messages.success(request, f"Stok untuk '{part.part_name}' telah disetujui dan diperbarui ke {part.quantity_in_stock}.")
            return redirect('dashboard')

        elif 'reject' in request.POST:
            reject_form = StockAdjustmentRejectForm(request.POST, instance=adjustment)
            if reject_form.is_valid():
                # 1. Update Adjustment Request
                adj = reject_form.save(commit=False)
                adj.status = 'Rejected'
                adj.managed_by = request.user
                adj.managed_at = timezone.now()
                adj.save()
                
                # 2. "Buka Kunci" Inventory
                part.status = 'Ready' # Kembalikan ke status normal
                if part.quantity_in_stock == 0:
                    part.status = 'Out_Of_Stock'
                part.save()
                
                messages.error(request, f"Permintaan penyesuaian untuk '{part.part_name}' telah ditolak.")
                return redirect('dashboard')

    context = {
        'adjustment': adjustment,
        'reject_form': reject_form
    }
    return render(request, 'app/approve_stock_adjustment.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def inventory_edit(request, part_id):
    # 1. Ambil data part yang ada dari database
    part = get_object_or_404(SparePartInventory, id=part_id)
    
    if request.method == 'POST':
        # 2. Isi form dengan data POST dan instance part yang ada
        form = SparePartInventoryForm(request.POST, instance=part)
        if form.is_valid():
            form.save()
            messages.success(request, f"Spare part '{part.part_name}' berhasil diperbarui.")
            return redirect('inventory_dashboard')
    else:
        # 3. Tampilkan form yang sudah terisi data (instance=part)
        form = SparePartInventoryForm(instance=part)
        
    context = {
        'form': form,
        'form_title': f'Edit Spare Part: {part.part_name}'
    }
    return render(request, 'app/inventory_form.html', context)

def _get_sku_history_context(sku_id):
    sku = get_object_or_404(SKU, id=sku_id)
    history_items = []
    if sku.po_number and sku.assigned_technician:
        history_items.append({
            'date': sku.created_at, 
            'type': 'Receiving',
            'actor': sku.po_number.approved_by_wm.username if sku.po_number.approved_by_wm else 'Sistem',
            'details': f"Diterima dari PO: {sku.po_number.po_number} dan ditugaskan ke {sku.assigned_technician.username}."
        })
    
    # 2. Info QC
    try:
        qc_form = QCForm.objects.get(sku=sku)
        details_qc = f"QC disubmit. Catatan: '{qc_form.condition_notes}'"
        if qc_form.qc_document_file:
            details_qc += f' <br><a href="{qc_form.qc_document_file.url}" target="_blank" class="fw-normal text-decoration-none"><i class="bi bi-file-earmark-arrow-down"></i> Download QC Form</a>'
        
        history_items.append({
            'date': qc_form.submitted_at, 
            'type': 'QC Submit',
            'actor': qc_form.technician.username,
            'details': details_qc 
        })
        
        # QC Approve / Reject
        if qc_form.managed_at: 
            if qc_form.is_approved_by_lead:
                history_items.append({
                    'date': qc_form.managed_at, 
                    'type': 'QC Approve',
                    'actor': 'Lead Tech' , 
                    'details': f"QC Disetujui. Komentar: '{qc_form.lead_technician_comments}'"
                })
            elif qc_form.lead_technician_comments:
                history_items.append({
                    'date': qc_form.managed_at, 
                    'type': 'QC Reject',
                    'actor': 'Lead Tech',
                    'details': f"QC Ditolak. Komentar: '{qc_form.lead_technician_comments}'"
                })

        # 3. Info Spare Part
        parts = SparePartRequest.objects.filter(qc_form=qc_form)
        for part in parts:
            history_items.append({
                'date': part.created_at, 
                'type': 'Spare Part',
                'actor': part.qc_form.technician.username,
                'details': f"Request part: {part.quantity_needed}x {part.part_name}. Status: {part.get_status_display()}"
            })
            if part.managed_at:
                actor_name = part.warehouse_manager.username if part.warehouse_manager else 'Warehouse'
                history_items.append({
                    'date': part.managed_at,
                    'type': 'Spare Part',
                    'actor': actor_name,
                    'details': f"Part {part.part_name} di-manage. Status: {part.get_status_display()}"
                })
                if part.lead_receipt_at:
                    actor_name = part.lead_receipt_approver.username if part.lead_receipt_approver else 'Lead Tech'
                    history_items.append({
                        'date': part.lead_receipt_at,
                        'type': 'Spare Part', # Anda bisa buat tipe baru 'Lead Receipt' jika mau
                        'actor': actor_name,
                        'details': f"Part {part.part_name} dikonfirmasi penerimaannya oleh Lead. Status: {part.get_status_display()}"
                    })
            if qc_form.installation_submitted_at:
                details_install = f"Form instalasi (B/A) disubmit. Catatan: '{qc_form.installation_notes}'"
                if qc_form.photo_before_install:
                    details_install += f' <br><a href="{qc_form.photo_before_install.url}" target="_blank" class="fw-normal text-decoration-none"><i class="bi bi-camera"></i> Lihat Foto Before</a>'
                if qc_form.photo_after_install:
                    details_install += f' <br><a href="{qc_form.photo_after_install.url}" target="_blank" class="fw-normal text-decoration-none"><i class="bi bi-camera-reels"></i> Lihat Foto After</a>'
            
                history_items.append({
                    'date': qc_form.installation_submitted_at,
                    'type': 'Install Submit',
                    'actor': qc_form.technician.username,
                    'details': details_install # Gunakan variabel details_install yang baru
                })
            if qc_form.final_managed_at:
                if qc_form.final_approval_at: 
                    history_items.append({
                        'date': qc_form.final_managed_at,
                        'type': 'Install Approve',
                        'actor': 'Lead Tech', 
                        'details': f"Instalasi disetujui. Komentar: '{qc_form.final_lead_comments}'"
                    })
                else: 
                    history_items.append({
                        'date': qc_form.final_managed_at,
                        'type': 'Install Reject',
                        'actor': 'Lead Tech',
                        'details': f"Instalasi ditolak. Komentar: '{qc_form.final_lead_comments}'"
                    })
    except QCForm.DoesNotExist:
        pass # Belum ada QC

    # 4. Info Penempatan Rak
    if sku.shelved_at: 
        history_items.append({
            'date': sku.shelved_at, 
            'type': 'Shelving',
            'actor': 'Warehouse',
            'details': f"Ditempatkan di rak: {sku.shelf_location}"
        })

    # 5. Info Movement
    movements = MovementRequest.objects.filter(sku_to_move=sku)
    for move in movements:
        details_kirim = f"Dikirim ke {move.requested_by_shop}."
        if move.delivery_form:
            details_kirim += f' <a href="{move.delivery_form.url}" target="_blank" class="fw-normal text-decoration-none">(Lihat Form DO)</a>'

        history_items.append({
            'date': move.created_at, 
            'type': 'Movement',
            'actor': 'Warehouse',
            'details': details_kirim # Menggunakan string baru
        })
        if move.received_at:
            details_terima = f"Dikonfirmasi diterima di {move.requested_by_shop}."
            if move.receipt_form:
                details_terima += f' <a href="{move.receipt_form.url}" target="_blank" class="fw-normal text-decoration-none">(Lihat Bukti Terima)</a>'

            history_items.append({
                'date': move.received_at,
                'type': 'Movement',
                'actor': 'Warehouse',
                'details': details_terima # Menggunakan string baru
            })
    # 6. Info Penjualan (Sales)
    # Ambil order paling baru yang terkait dengan SKU ini
    sales_order = SalesOrder.objects.filter(sku=sku).order_by('-created_at').first()
    
    if sales_order:
        history_items.append({
            'date': sales_order.created_at,
            'type': 'Sales Order',
            'actor': sales_order.sales_person.username,
            'details': f"Order dibuat untuk: <strong>{sales_order.customer_name}</strong>. Status: {sales_order.get_status_display()}"
        })

        # 7. Info Pembayaran
        payments = Payment.objects.filter(sales_order=sales_order).order_by('payment_date')
        for payment in payments:
            # Format angka dengan koma
            amount_formatted = "{:,.0f}".format(payment.amount).replace(",", ".")
            history_items.append({
                'date': payment.payment_date,
                'type': 'Payment',
                'actor': sales_order.sales_person.username,
                'details': f"Pembayaran diterima <strong>Rp {amount_formatted}</strong>. <a href='{payment.proof_of_transfer.url}' target='_blank' class='fw-normal text-decoration-none'>(Lihat Bukti)</a>"
            })

        # 8. Info Pengiriman (Shipping)
        if sales_order.shipped_at:
            details_shipping = f"Dikirim ke {sales_order.customer_name}."
            if sales_order.shipping_type:
                details_shipping += f" Tipe: {sales_order.shipping_type}."
            if sales_order.shipping_receipt:
                 details_shipping += f" <a href='{sales_order.shipping_receipt.url}' target='_blank' class='fw-normal text-decoration-none'>(Lihat Resi)</a>"
            
            history_items.append({
                'date': sales_order.shipped_at,
                'type': 'Shipping',
                'actor': sales_order.sales_person.username,
                'details': details_shipping
            })
        
        # 9. Info Penerimaan (Completed)
        if sales_order.completed_at:
            history_items.append({
                'date': sales_order.completed_at,
                'type': 'Completed',
                'actor': sales_order.customer_name, # Aktornya adalah customer
                'details': f"Diterima oleh customer. <a href='{sales_order.proof_of_receipt.url}' target='_blank' class='fw-normal text-decoration-none'>(Lihat Bukti Terima)</a>"
            })
    if history_items:
        history_items.sort(key=lambda x: x['date'] or timezone.now(), reverse=True)

    return {
        'sku': sku,
        'history_items': history_items
    }

@login_required(login_url='login')
def sku_history(request, sku_id):
    context = _get_sku_history_context(sku_id)
    return render(request, 'app/sku_history.html', context)

@login_required(login_url='login')
def get_sku_history_modal(request, sku_id):
    context = _get_sku_history_context(sku_id)
    # Render template parsial yang baru kita buat
    return render(request, 'app/_includes/sku_history_modal_content.html', context)

@login_required(login_url='login')
@user_passes_test(is_purchasing)
def po_create(request):
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            po.status = 'Pending_Approval' # Status awal
            po.save()
            messages.success(request, f"PO {po.po_number} berhasil dibuat dan menunggu approval WM.")
            return redirect('dashboard')
    else:
        form = PurchaseOrderForm()
        
    context = {'form': form}
    return render(request, 'app/po_create.html', context)

# --- Alur PO (Warehouse Manager) ---
@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def po_approve_list(request):
    pending_pos = PurchaseOrder.objects.filter(status='Pending_Approval').order_by('-id')
    context = {'pending_pos': pending_pos}
    return render(request, 'app/po_approve_list.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def po_approve_detail(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id, status='Pending_Approval')
    
    if request.method == 'POST':
        if 'approve' in request.POST:
            po.status = 'Pending' 
            po.approved_by_wm = request.user
            po.managed_at = timezone.now()
            po.rejection_reason = None
            po.save()
            messages.success(request, f"PO {po.po_number} telah disetujui.")
            return redirect('po_approve_list')
            
        elif 'reject' in request.POST:
            reject_form = PORejectionForm(request.POST, instance=po)
            if reject_form.is_valid():
                po = reject_form.save(commit=False)
                po.status = 'Rejected'
                po.approved_by_wm = request.user
                po.managed_at = timezone.now()
                po.save()
                messages.error(request, f"PO {po.po_number} telah ditolak.")
                return redirect('po_approve_list')
        
    reject_form = PORejectionForm(instance=po)
    context = {
        'po': po,
        'reject_form': reject_form
    }
    return render(request, 'app/po_approve_detail.html', context)

# --- Receiving ---
@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def receiving_list(request):
    all_pos = PurchaseOrder.objects.filter(
        status__in=['Pending', 'Delivered', 'Finished']
    ).order_by('-id')
    
    context = { 'purchase_orders': all_pos }
    return render(request, 'app/receiving_list.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def receiving_detail(request, po_id):
    po = get_object_or_404(PurchaseOrder.objects.exclude(status__in=['Pending_Approval', 'Rejected']), id=po_id)

    if request.method == 'POST':
        if 'add_sku' in request.POST:
            sku_id = request.POST.get('sku_id')
            sku_name = request.POST.get('sku_name')
            technician_id = request.POST.get('technician')
            assigned_technician = User.objects.get(id=technician_id)

            SKU.objects.create(
                po_number=po,
                sku_id=sku_id,
                name=sku_name,
                assigned_technician=assigned_technician,
                status='QC'
            )

            po.status = 'Delivered'
            current_sku_count = po.skus.count()
            if current_sku_count >= po.expected_sku_count:
                po.status = 'Finished'
            po.save()

        elif 'upload_dr' in request.POST:
            dr_file = request.FILES.get('delivery_receipt_file')
            if dr_file:
                po.delivery_receipt = dr_file
                po.save()

        elif 'packing_list_not_ok' in request.POST:
            rejection_message = request.POST.get('rejection_message')
            if rejection_message:
                PurchasingNotification.objects.create(
                    po_number=po,
                    message=rejection_message,
                    reported_by=request.user
                )
                po.status = 'Pending' 
                po.save()
                return redirect('receiving_list') 

        return redirect('receiving_detail', po_id=po.id)

    skus_in_po = po.skus.all()
    technicians = User.objects.filter(groups__name='Technician')
    context = {
        'po': po,
        'skus_in_po': skus_in_po,
        'technicians': technicians
    }
    return render(request, 'app/receiving_detail.html', context)

@login_required(login_url='login')
@user_passes_test(is_technician)
def qc_form(request, sku_id):
    sku = get_object_or_404(SKU, id=sku_id, assigned_technician=request.user)
    try:
        existing_form = QCForm.objects.get(sku=sku)
    except QCForm.DoesNotExist:
        existing_form = None

    if request.method == 'POST':
        notes = request.POST.get('condition_notes')
        needs_spare_part = request.POST.get('needs_spare_part') == 'on'
        part_name = request.POST.get('part_name', '')
        part_qty = request.POST.get('part_qty', 1)
        qc_file = request.FILES.get('qc_document_file') 
        qc_obj, created = QCForm.objects.get_or_create(
            sku=sku, 
            defaults={'technician': request.user, 'condition_notes': notes}
        )
        
        if not created:
            qc_obj.condition_notes = notes
            qc_obj.is_approved_by_lead = False
            qc_obj.lead_technician_comments = None 
        if qc_file:
            qc_obj.qc_document_file = qc_file
        qc_obj.save()
        old_requests = SparePartRequest.objects.filter(
            qc_form=qc_obj, 
            status__in=['Pending', 'Rejected'] 
        )
        old_requests.delete()

        # Buat request baru jika diperlukan
        if needs_spare_part and part_name:
            SparePartRequest.objects.create(
                qc_form=qc_obj,
                part_name=part_name,
                quantity_needed=part_qty,
                status='Pending'
            )

        sku.status = 'QC_PENDING' 
        sku.save()

        return redirect('dashboard')

    # Kirim 'existing_form' ke template
    context = {
        'sku': sku,
        'existing_form': existing_form 
    }
    return render(request, 'app/qc_form.html', context)

@login_required(login_url='login')
@user_passes_test(is_lead_technician)
def qc_verify(request, qc_id):
    qc_form = get_object_or_404(QCForm, id=qc_id)
    sku = qc_form.sku

    if request.method == 'POST':
        if 'approve' in request.POST:
            qc_form.is_approved_by_lead = True
            qc_form.lead_technician_comments = request.POST.get('comments', 'Disetujui.')
            qc_form.managed_at = timezone.now()
            qc_form.save()

            has_pending_parts = SparePartRequest.objects.filter(qc_form=qc_form, status='Pending').exists()

            if not has_pending_parts:
                sku.status = 'Ready'
                sku.save()

        elif 'reject' in request.POST:
            qc_form.is_approved_by_lead = False 
            qc_form.lead_technician_comments = request.POST.get('comments', 'Ditolak. Harap perbaiki.')
            qc_form.managed_at = timezone.now()
            qc_form.save()

            # Ubah status spare part request yang pending menjadi 'Rejected'
            pending_parts = SparePartRequest.objects.filter(qc_form=qc_form, status='Pending')
            for part in pending_parts:
                part.status = 'Rejected'
                part.save()

            technician_user = qc_form.technician
            analytics, created = TechnicianAnalytics.objects.get_or_create(technician=technician_user)
            analytics.wrong_qc_count += 1
            analytics.save()

            sku.status = 'QC'
            sku.save()

        return redirect('dashboard') 

    context = {
        'qc_form': qc_form,
        'sku': sku,
        'part_requests': qc_form.part_requests.all() 
    }
    return render(request, 'app/qc_verify.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager) 
def manage_sparepart(request, request_id):
    part_request = get_object_or_404(SparePartRequest, id=request_id)
    qc_form = part_request.qc_form
    sku = qc_form.sku

    # Cek stok yang ada di inventory
    try:
        inventory_item = SparePartInventory.objects.get(part_name__iexact=part_request.part_name)
        current_stock = inventory_item.quantity_in_stock
    except SparePartInventory.DoesNotExist:
        inventory_item = None
        current_stock = 0

    if request.method == 'POST':
        if 'issue_part' in request.POST:
            if inventory_item and inventory_item.quantity_in_stock >= part_request.quantity_needed:
                
                # --- LOGIKA AUTO-DEDUCTION ---
                inventory_item.quantity_in_stock -= part_request.quantity_needed
                inventory_item.save()
                part_request.status = 'PENDING_LEAD_RECEIPT' 
                part_request.warehouse_manager = request.user
                part_request.managed_at = timezone.now()
                part_request.save()
            else:
                messages.error(request, "Stok tidak mencukupi untuk 'Issue Part'.")

        elif 'approve_buy' in request.POST:
            part_request.status = 'Approved_Buy'
            part_request.warehouse_manager = request.user
            part_request.managed_at = timezone.now()
            part_request.save()
            messages.info(request, "Request pembelian telah diteruskan ke Purchasing.")

        return redirect('dashboard')

    context = {
        'part_request': part_request,
        'sku': sku,
        'current_stock': current_stock, # Kirim info stok ke template
        'inventory_item': inventory_item # Kirim item inventory
    }
    return render(request, 'app/manage_sparepart.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager) 
def assign_shelf(request, sku_id):
    sku = get_object_or_404(SKU, id=sku_id, status='Ready')

    if request.method == 'POST':
        shelf_location_input = request.POST.get('shelf_location')

        sku.shelf_location = shelf_location_input
        sku.shelved_at = timezone.now()
        sku.save()

        return redirect('dashboard') 

    context = {
        'sku': sku
    }
    return render(request, 'app/assign_shelf.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager) 
def movement_process(request):

    if request.method == 'POST':

        if 'create_movement' in request.POST:
            sku_id = request.POST.get('sku_id')
            requested_by = request.POST.get('requested_by_shop')
            delivery_form_file = request.FILES.get('delivery_form')

            sku_to_move = get_object_or_404(SKU, id=sku_id)

            MovementRequest.objects.create(
                sku_to_move=sku_to_move,
                requested_by_shop=requested_by,
                delivery_form=delivery_form_file,
                status='Delivering' 
            )

            sku_to_move.status = 'Delivering'
            sku_to_move.save()

        elif 'confirm_received' in request.POST:
            movement_id = request.POST.get('movement_id')
            receipt_file = request.FILES.get('receipt_form_file') 
            
            movement = get_object_or_404(MovementRequest, id=movement_id)
            if receipt_file:
                movement.receipt_form = receipt_file 
                movement.status = 'Received'
                movement.received_at = timezone.now()
                movement.save()

                sku = movement.sku_to_move
                sku.status = 'Shop'
                sku.location = 'Shop' 
                sku.save()
                messages.success(request, f"Penerimaan SKU {sku.sku_id} telah dikonfirmasi.")
            else:
                messages.error(request, "Gagal konfirmasi. Anda wajib mengupload bukti penerimaan.")
        return redirect('movement_process')

    skus_ready_to_move = SKU.objects.filter(
        status='Ready',
        shelf_location__isnull=False 
    )

    movements_in_progress = MovementRequest.objects.filter(status='Delivering')

    context = {
        'skus_ready_to_move': skus_ready_to_move,
        'movements_in_progress': movements_in_progress
    }
    return render(request, 'app/movement_process.html', context)

@login_required(login_url='login')
@user_passes_test(is_purchasing)
def mark_part_received(request, request_id):
    if request.method == 'POST':
        part_request = get_object_or_404(SparePartRequest, id=request_id)
        part_request.status = 'Received'
        part_request.received_at = timezone.now()
        part_request.save()
        try:
            inventory_item = SparePartInventory.objects.get(part_name__iexact=part_request.part_name)
            inventory_item.quantity_in_stock += part_request.quantity_needed
            if inventory_item.status == 'Out_Of_Stock' or inventory_item.status == 'On_Order':
                inventory_item.status = 'Ready' 
            inventory_item.save()
        except SparePartInventory.DoesNotExist:
            # Jika part ini baru, buat entri inventory baru
            SparePartInventory.objects.create(
                part_name=part_request.part_name,
                quantity_in_stock=part_request.quantity_needed,
                status='Ready',
                origin='PURCHASE'
            )
        messages.success(request, f"Stok {part_request.part_name} telah ditambahkan ke inventory.")

    return redirect('dashboard')

class SignUpView(generic.CreateView):
    form_class = CustomUserCreationForm 

    success_url = reverse_lazy('login') 
    template_name = 'app/register.html' 

    def form_valid(self, form):
        response = super().form_valid(form)
        selected_group = form.cleaned_data['role']
        self.object.groups.add(selected_group)
        return response

@login_required(login_url='login')
@user_passes_test(is_lead_technician)
def approve_part_receipt(request, part_id):
    """
    View untuk Lead Tech menyetujui penerimaan spare part dari Warehouse.
    """
    part_request = get_object_or_404(SparePartRequest, id=part_id, status='PENDING_LEAD_RECEIPT')
    qc_form = part_request.qc_form
    sku = qc_form.sku

    if request.method == 'POST':
        if 'approve' in request.POST:
            # 1. Setujui part request
            part_request.status = 'Issued' # Sekarang resmi 'Issued'
            part_request.lead_receipt_approver = request.user
            part_request.lead_receipt_at = timezone.now()
            part_request.save()

            # 2. Cek apakah ada part lain yang masih 'Pending' untuk SKU ini
            other_pending_parts = SparePartRequest.objects.filter(
                qc_form=qc_form, 
                status__in=['Pending', 'Approved_Buy', 'Received', 'PENDING_LEAD_RECEIPT']
            ).exists()

            # 3. Jika TIDAK ADA part lain, baru ubah status SKU
            if not other_pending_parts:
                sku.status = 'AWAITING_INSTALL'
                sku.save()
                messages.success(request, f"Penerimaan part {part_request.part_name} disetujui. Tugas instalasi telah diteruskan ke teknisi.")
            else:
                messages.success(request, f"Penerimaan part {part_request.part_name} disetujui. Masih menunggu part lain.")
            
            return redirect('dashboard')

        elif 'reject' in request.POST:
            # Jika ditolak, kembalikan ke WM
            part_request.status = 'Pending' 
            part_request.save()
            messages.error(request, f"Penerimaan part ditolak. Request dikembalikan ke Warehouse Manager.")
            return redirect('dashboard')

    context = {
        'part_request': part_request,
        'sku': sku
    }
    return render(request, 'app/approve_part_receipt.html', context)

@login_required(login_url='login')
@user_passes_test(is_technician)
def installation_form(request, qc_id):
    qc_form = get_object_or_404(QCForm, id=qc_id, sku__assigned_technician=request.user)
    sku = qc_form.sku

    if sku.status != 'AWAITING_INSTALL':
        messages.error(request, "SKU ini tidak sedang menunggu instalasi part.")
        return redirect('dashboard')

    if request.method == 'POST':
        # Update catatan umum
        qc_form.installation_notes = request.POST.get('installation_notes')
        qc_form.installation_submitted_at = timezone.now()
        qc_form.final_lead_comments = None
        qc_form.save()

        # --- LOGIKA BARU: MULTIPLE UPLOAD BEFORE ---
        before_images = request.FILES.getlist('before_photos')
        before_remarks = request.POST.getlist('before_remarks')
        
        # Menggunakan zip untuk memasangkan foto dengan remarks-nya
        for img, remark in zip(before_images, before_remarks):
            InstallationPhoto.objects.create(
                qc_form=qc_form,
                image=img,
                photo_type='before',
                remarks=remark
            )

        # --- LOGIKA BARU: MULTIPLE UPLOAD AFTER ---
        after_images = request.FILES.getlist('after_photos')
        after_remarks = request.POST.getlist('after_remarks')

        for img, remark in zip(after_images, after_remarks):
            InstallationPhoto.objects.create(
                qc_form=qc_form,
                image=img,
                photo_type='after',
                remarks=remark
            )
        has_old_part = request.POST.get('has_old_part') == 'on'
        old_part_name = request.POST.get('old_part_name', '')

        # Hapus data part lama sebelumnya jika ada (untuk re-submit)
        ReturnedPart.objects.filter(qc_form=qc_form, status='Pending_Lead').delete()

        if has_old_part and old_part_name:
            ReturnedPart.objects.create(
                qc_form=qc_form,
                part_name_reported=old_part_name,
                status='Pending_Lead'
            )
        # Update status SKU
        sku.status = 'PENDING_FINAL_CHECK'
        sku.save()
        
        messages.success(request, f"Form instalasi untuk SKU {sku.sku_id} telah disubmit.")
        return redirect('dashboard')

    context = {
        'qc_form': qc_form,
        'sku': sku
    }
    return render(request, 'app/installation_form.html', context)

@login_required(login_url='login')
@user_passes_test(is_warehouse_manager)
def get_part_usage_history(request, part_name):
    # Cari request part yang sudah status Issued atau Received (artinya sudah dipakai/diproses)
    history_usage = SparePartRequest.objects.filter(
        part_name__iexact=part_name,
        status__in=['Issued', 'Received', 'Approved_Buy', 'PENDING_LEAD_RECEIPT']
    ).select_related('qc_form__sku', 'qc_form__technician').order_by('-created_at')

    # Kita render potongan HTML kecil (partial)
    html_content = render_to_string('app/_includes/part_history_modal_content.html', {
        'part_name': part_name,
        'history_usage': history_usage
    })
    
    return JsonResponse({'html': html_content})

@login_required(login_url='login')
@user_passes_test(is_lead_technician)
def final_check(request, qc_id):
    qc_form = get_object_or_404(QCForm, id=qc_id)
    sku = qc_form.sku
    returned_part = ReturnedPart.objects.filter(
        qc_form=qc_form, 
        status='Pending_Lead'
    ).first()
    if sku.status != 'PENDING_FINAL_CHECK':
        messages.error(request, "SKU ini tidak sedang menunggu final check.")
        return redirect('dashboard')

    if request.method == 'POST':
        comments = request.POST.get('comments', '')
        lead_assigned_sku = request.POST.get('lead_assigned_sku', '')
        if 'approve' in request.POST:
            if returned_part and not lead_assigned_sku:
                messages.error(request, "APPROVAL GAGAL: Anda wajib mengisi Nomor SKU untuk sparepart lama yang dikembalikan.")
                context = {
                    'qc_form': qc_form,
                    'sku': sku,
                    'returned_part': returned_part # Kirim ini agar formnya muncul lagi
                }
                return render(request, 'app/final_check.html', context)
            qc_form.final_lead_comments = comments if comments else "Instalasi disetujui."
            qc_form.final_approval_at = timezone.now()
            qc_form.final_managed_at = timezone.now()
            qc_form.save()
            sku.status = 'Ready'
            sku.save()
            if returned_part:
                returned_part.status = 'Approved'
                returned_part.lead_assigned_sku = lead_assigned_sku
                returned_part.approved_by_lead = request.user
                returned_part.managed_at = timezone.now()
                returned_part.save()
                part_inventory, created = SparePartInventory.objects.get_or_create(
                    part_sku=lead_assigned_sku,
                    defaults={
                        'part_name': returned_part.part_name_reported,
                        'quantity_in_stock': 1,
                        'status': 'Ready',
                        'origin': 'RETURN' 
                    }
                )
                
                if not created:
                    # Jika part sudah ada, tambahkan stoknya
                    part_inventory.quantity_in_stock += 1
                    part_inventory.status = 'Ready'
                    # Pastikan origin-nya ter-update jika sebelumnya bukan 'RETURN'
                    part_inventory.origin = 'RETURN' 
                    part_inventory.save()
            messages.success(request, f"Instalasi SKU {sku.sku_id} telah disetujui. SKU sekarang 'Ready'.")

        elif 'reject' in request.POST:
            if not comments:
                messages.error(request, "Komentar wajib diisi jika me-reject.")
                return redirect('final_check', qc_id=qc_id)
                
            qc_form.final_lead_comments = comments
            qc_form.final_approval_at = None # Reset
            qc_form.final_managed_at = timezone.now()
            qc_form.save()

            # Kembalikan status ke Teknisi
            sku.status = 'AWAITING_INSTALL'
            sku.save()
            if returned_part:
                returned_part.status = 'Rejected' # Ditolak
                returned_part.managed_at = timezone.now()
                returned_part.save()
                
            messages.warning(request, f"Instalasi SKU {sku.sku_id} ditolak dan dikembalikan ke teknisi.")
            return redirect('dashboard')
    context = {
        'qc_form': qc_form,
        'sku': sku,
        'returned_part': returned_part
    }
    return render(request, 'app/final_check.html', context)

@login_required(login_url='login')
def inventory_search_api(request):
    query = request.GET.get('q', '')
    results = []
    
    if query:
        parts = SparePartInventory.objects.filter(
            Q(part_name__icontains=query) | 
            Q(part_sku__icontains=query)
        ).order_by('-quantity_in_stock')[:10] # Limit 10 hasil
        
        for part in parts:
            results.append({
                'name': part.part_name,
                'stock': part.quantity_in_stock,
                'location': part.location or '-',
                'sku_part': part.part_sku or '-',
                'supplier': part.primary_supplier or '-'
            })
            
    return JsonResponse(results, safe=False)