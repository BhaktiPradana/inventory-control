from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib import messages
from django.contrib.staticfiles.finders import find as find_static 
from django.urls import reverse_lazy
from django.views import generic
from django.db.models import Count, Q, Sum 
from django.db import transaction
from django.db import IntegrityError
from django.utils import timezone
from django.http import JsonResponse
from django.http import HttpResponse
from django.conf import settings
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.pdfgen import canvas
from django.template.loader import render_to_string
from .models import (
    PurchaseOrder, SKU, QCForm, SparePartRequest, 
    TechnicianAnalytics, MovementRequest, PurchasingNotification, SparePartInventory, StockAdjustment, ReturnedPart, InstallationPhoto, SalesOrder, Payment, Quotation, Rack
)
from .models import Store, SalesAssignment, User, Group
from .forms import CustomUserCreationForm, PurchaseOrderForm, PORejectionForm, SparePartInventoryForm, StockAdjustmentForm, StockAdjustmentRejectForm, SalesOrderForm, PaymentForm, ShippingFileForm, QuotationForm, StoreForm, SalesAssignmentForm, MovementRequestForm, RackSelectionForm, RackForm
import textwrap
import os
from functools import wraps


styles = getSampleStyleSheet()
styleN = styles['Normal']
styleN.fontName = 'Helvetica'
styleN.fontSize = 9
styleN.leading = 11

# --- Cek Role ---
def is_master_role(user):
    """Cek apakah user adalah anggota grup 'Master Role'."""
    return user.groups.filter(name='Master Role').exists()
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
def intcomma(value):
    """Format an integer with commas."""
    if isinstance(value, (float, int)):
        return f"{int(value):,}".replace(",", ".")
    return str(value)
def has_permission_or_is_master(user, required_group_name):
    """
    Mengembalikan True jika user adalah Master Role ATAU user adalah 
    anggota dari grup yang diwajibkan (required_group_name).
    """
    if is_master_role(user):
        return True
    return user.groups.filter(name=required_group_name).exists()


@login_required
@user_passes_test(is_master_role)
def master_role_dashboard(request):
    """
    Dashboard Master Role:
    - Sidebar: Link ke Store Management dan Sales Assignment.
    - Fungsionalitas: View dan Edit data dari semua model.
    """
    stores = Store.objects.all()
    assignments = SalesAssignment.objects.select_related('sales_person', 'assigned_store').all()
    
    context = {
        'stores': stores,
        'assignments': assignments,
        'total_stores': stores.count(),
        'total_sales_assigned': assignments.count(),
        'total_users': User.objects.count(),
    }
    return render(request, 'app/dashboards/master_role_dashboard.html', context)


# --- Store Management ---
@login_required
@user_passes_test(is_master_role)
def store_list(request):
    stores = Store.objects.all()
    return render(request, 'app/store_list.html', {'stores': stores})

@login_required
@user_passes_test(is_master_role)
def store_add(request):
    if request.method == 'POST':
        form = StoreForm(request.POST) 
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Store baru berhasil ditambahkan.')
                return redirect('store_list')
            except IntegrityError:
                messages.error(request, 'Nama Store sudah ada. Mohon gunakan nama yang unik.')
        else:
            messages.error(request, 'Gagal menambahkan Store. Cek data yang diinput.')
    else:
        form = StoreForm()
    return render(request, 'app/store_form.html', {'form': form, 'title': 'Tambah Store Baru'})

@login_required
@user_passes_test(is_master_role)
def store_edit(request, store_id):
    store = get_object_or_404(Store, id=store_id)
    if request.method == 'POST':
        form = StoreForm(request.POST, instance=store)
        if form.is_valid():
            form.save()
            messages.success(request, f'Store **{store.name}** berhasil diupdate.')
            return redirect('store_list')
    else:
        form = StoreForm(instance=store)
    return render(request, 'app/store_form.html', {'form': form, 'title': f'Edit Store: {store.name}'})

@login_required
@user_passes_test(is_master_role)
def store_delete(request, store_id):
    store = get_object_or_404(Store, id=store_id)
    # Periksa jika ada Sales yang masih terikat
    if store.assigned_sales.exists():
        messages.error(request, f'Tidak bisa menghapus Store **{store.name}** karena masih ada Sales yang ditugaskan di sini. Pindahkan Sales terlebih dahulu.')
        return redirect('store_list') # Atau ke halaman detail store
        
    # Periksa jika ada SKU yang masih terikat
    if store.skus_in_store.exists():
        messages.error(request, f'Tidak bisa menghapus Store **{store.name}** karena masih ada SKU yang berlokasi di sini. Pindahkan SKU terlebih dahulu.')
        return redirect('store_list') # Atau ke halaman detail store
        
    if request.method == 'POST':
        store.delete()
        messages.success(request, f'Store **{store.name}** berhasil dihapus.')
        return redirect('store_list')
    # Jika perlu konfirmasi:
    context = {'store': store}
    return render(request, 'app/store_confirm_delete.html', context)


# --- Sales Assignment Management ---
@login_required
@user_passes_test(is_master_role)
def sales_assignment_list(request):
    assignments = SalesAssignment.objects.select_related('sales_person', 'assigned_store').all()
    # List Sales yang belum punya Store
    assigned_sales_ids = [a.sales_person.id for a in assignments]
    unassigned_sales = User.objects.filter(groups__name='Sales').exclude(id__in=assigned_sales_ids)

    context = {
        'assignments': assignments,
        'unassigned_sales': unassigned_sales,
    }
    return render(request, 'app/sales_assignment_list.html', context)

@login_required
@user_passes_test(is_master_role)
def sales_assignment_add(request):
    if request.method == 'POST':
        form = SalesAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.assigned_by = request.user # Set Master Role
            try:
                assignment.save()
                messages.success(request, f'Sales **{assignment.sales_person.username}** berhasil ditugaskan di **{assignment.assigned_store.name}**.')
                return redirect('sales_assignment_list')
            except IntegrityError:
                messages.error(request, 'Sales tersebut sudah memiliki Store yang ditugaskan.')
        else:
            messages.error(request, 'Gagal menugaskan Sales. Cek data yang diinput.')
    else:
        form = SalesAssignmentForm()
    return render(request, 'app/sales_assignment_form.html', {'form': form, 'title': 'Tugaskan Sales ke Store'})

@login_required
@user_passes_test(is_master_role)
def sales_assignment_edit(request, assignment_id):
    assignment = get_object_or_404(SalesAssignment, id=assignment_id)
    # Batasi agar Sales Person tidak bisa diubah (karena OneToOne), hanya Store yang diubah
    if request.method == 'POST':
        # Gunakan SalesAssignmentForm dan exclude 'sales_person' jika perlu, 
        # atau pastikan sales_person di-disabled di form.
        form = SalesAssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            # Set ulang assigned_by untuk menandai siapa yang mengubah
            assignment.assigned_by = request.user
            assignment.save()
            messages.success(request, f'Penugasan Sales **{assignment.sales_person.username}** berhasil diupdate ke **{assignment.assigned_store.name}**.')
            return redirect('sales_assignment_list')
    else:
        form = SalesAssignmentForm(instance=assignment)
        # Nonaktifkan field sales_person
        form.fields['sales_person'].disabled = True 

    return render(request, 'app/sales_assignment_form.html', {'form': form, 'title': f'Edit Penugasan: {assignment.sales_person.username}'})


def rack_manager_required(function=None):
    def check_user(user):
        return is_master_role(user) or is_warehouse_manager(user)
    actual_decorator = user_passes_test(check_user, login_url='login')
    if function:
        return actual_decorator(function)
    return actual_decorator

@login_required
@rack_manager_required
def rack_grid_view(request):
    """Menampilkan grid rak seperti pemilihan kursi bioskop."""
    
    # Ambil semua data rack. Grouping berdasarkan prefiks (cth: 'A', 'B', ...)
    racks = Rack.objects.all().order_by('rack_location')
    
    # Membuat struktur data untuk grid view: {'A': [RackObj1, RackObj2], 'B': [...], ...}
    rack_grid = {}
    for rack in racks:
        # Asumsi format rack_location adalah A1-01, A2-01, dll. atau hanya A, B, C...
        # Kita ambil huruf pertama sebagai "Baris/Area" (A, B, C...)
        prefix = rack.rack_location[0].upper()
        if prefix not in rack_grid:
            rack_grid[prefix] = []
        rack_grid[prefix].append(rack)

    context = {
        'rack_grid': rack_grid,
        'rack_rows': sorted(rack_grid.keys()),
    }
    return render(request, 'app/rack_grid_view.html', context)

@login_required
@rack_manager_required
def rack_list(request):
    """Menampilkan daftar semua rak."""
    racks = Rack.objects.select_related('occupied_by_sku').all().order_by('rack_location')
    context = {
        'racks': racks
    }
    return render(request, 'app/rack_list.html', context)

@login_required
@rack_manager_required
def rack_add(request):
    if request.method == 'POST':
        form = RackForm(request.POST)
        if form.is_valid():
            try:
                rack = form.save(commit=False)
                # Status default saat add adalah 'Available'
                rack.status = 'Available'
                rack.save()
                messages.success(request, f'Rak **{rack.rack_location}** berhasil ditambahkan.')
                return redirect('rack_list')
            except IntegrityError:
                messages.error(request, 'Lokasi Rak sudah ada. Mohon gunakan nama yang unik.')
        else:
            messages.error(request, 'Gagal menambahkan Rak. Cek data yang diinput.')
    else:
        form = RackForm()
        
    context = {
        'form': form,
        'title': 'Tambah Rak Baru'
    }
    return render(request, 'app/rack_form.html', context)

@login_required
@rack_manager_required
def rack_edit(request, rack_id):
    rack = get_object_or_404(Rack, id=rack_id)
    
    # Jika rak sedang ditempati, kita tidak mengizinkan edit rack_location
    initial_data = {}
    if rack.occupied_by_sku:
        # Jika rak terisi, kita tidak ingin user mengubah status manual (Status field sudah di disable di RackForm)
        messages.warning(request, f"Rak **{rack.rack_location}** sedang terisi oleh SKU {rack.occupied_by_sku.sku_id}. Hanya lokasi dan status yang tidak terikat yang dapat diubah.")

    if request.method == 'POST':
        form = RackForm(request.POST, instance=rack)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Rak **{rack.rack_location}** berhasil diupdate.')
                return redirect('rack_list')
            except IntegrityError:
                messages.error(request, 'Lokasi Rak sudah ada. Mohon gunakan nama yang unik.')
        else:
            messages.error(request, 'Gagal mengupdate Rak. Cek data yang diinput.')
    else:
        form = RackForm(instance=rack)
        # Nonaktifkan field lokasi jika rak sedang terisi (untuk keamanan data)
        if rack.occupied_by_sku:
             form.fields['rack_location'].disabled = True

    context = {
        'form': form,
        'rack': rack,
        'title': f'Edit Rak: {rack.rack_location}'
    }
    return render(request, 'app/rack_form.html', context)

@login_required
@rack_manager_required
def rack_delete(request, rack_id):
    rack = get_object_or_404(Rack, id=rack_id)
    
    # Cek keterikatan
    if rack.occupied_by_sku:
        messages.error(request, f'Tidak bisa menghapus Rak **{rack.rack_location}** karena masih ditempati oleh SKU {rack.occupied_by_sku.sku_id}. Kosongkan rak tersebut terlebih dahulu.')
        return redirect('rack_list')

    if request.method == 'POST':
        rack.delete()
        messages.success(request, f'Rak **{rack.rack_location}** berhasil dihapus.')
        return redirect('rack_list')

    context = {'rack': rack}
    return render(request, 'app/rack_confirm_delete.html', context)

@login_required(login_url='login') 
def dashboard(request):
    user = request.user 
    if is_master_role(user) or user.is_superuser:
        context = {
            'total_users': User.objects.count(), 
        }
        return master_role_dashboard(request)
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
        history_pos = PurchaseOrder.objects.exclude(status='Pending_Approval').order_by('-created_at')
        search_query = request.GET.get('po_search', '')
        if search_query:
            history_pos = history_pos.filter(po_number__icontains=search_query)
        context = {
            'parts_to_buy': parts_to_buy,
            'po_notifications': po_notifications,
            'rejected_pos': rejected_pos,
            'pending_adjustments': pending_adjustments,
            'history_pos': history_pos, 
            'search_query': search_query 
        }
        context.update(sidebar_context) 
        context.update(ready_list_context)
        return render(request, 'app/dashboards/purchasing_dashboard.html', context)
    elif is_sales(user):
        try:
            sales_assignment = SalesAssignment.objects.get(sales_person=user)
            my_store = sales_assignment.assigned_store
        except SalesAssignment.DoesNotExist:
            my_store = None
            messages.warning(request, "Anda belum ditugaskan ke Store manapun oleh Master Role.")

        # Ambil semua order dan quotation (tetap)
        my_orders = SalesOrder.objects.filter(
            sales_person=user
        ).select_related('sku').prefetch_related('payments').order_by('-created_at')

        my_quotations = Quotation.objects.filter(
            sales_person=user
        ).select_related('sku').order_by('-created_at')

        add_order_form = SalesOrderForm()
        add_quotation_form = QuotationForm()

        # REVISI 1 & 2: Ambil Movement yang ditujukan ke Store Sales ini dan statusnya 'Delivering'
        movements_in_transit = MovementRequest.objects.filter(
            requested_by_store=my_store,
            status='Delivering'
        ).select_related('sku_to_move', 'requested_by_store').order_by('-created_at')

        context = {
            'my_orders': my_orders,
            'my_quotations': my_quotations, 
            'add_order_form': add_order_form,
            'add_quotation_form': add_quotation_form, 
            'my_store': my_store, # Store Sales saat ini
            'movements_in_transit': movements_in_transit, # Daftar SKU yang harus diterima
        }
        # Sales juga bisa melihat list SKU Ready dan Ready Store
        context.update(sidebar_context) 
        context.update(ready_list_context) 
        return render(request, 'app/dashboards/sales_dashboard.html', context)

    # Fallback jika tidak punya role
    return render(request, 'app/dashboard.html')

def sales_or_master_required(function=None):
    def check_user(user):
        return is_master_role(user) or user.groups.filter(name='Sales').exists()
    actual_decorator = user_passes_test(check_user, login_url='login')
    if function:
        return actual_decorator(function)
    return actual_decorator

@login_required(login_url='login')
@sales_or_master_required
def sales_order_add(request):
    """View untuk memproses form '+ Add Customer'."""
    if request.method == 'POST':
        form = SalesOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.sales_person = request.user
            order.status = 'Pending' # Status awal, belum ada pembayaran
            order.save()
            
            messages.success(request, f"Order untuk {order.customer_name} berhasil dibuat. Invoice akan dicetak otomatis.")
            return redirect(f"{reverse('sales_order_detail', args=[order.id])}?print=true")
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
                'add_order_form': form,
                'sidebar_skus_under_tech': skus_under_tech,
                'ready_skus_list': ready_skus_list,
                'shop_skus_list': shop_skus_list
            }
            messages.error(request, "Gagal menambahkan order. Cek error di bawah form.")
            return render(request, 'app/dashboards/sales_dashboard.html', context)
            
    return redirect('dashboard') # Jika bukan POST, kembalikan ke dashboard

@login_required(login_url='login')
@user_passes_test(is_sales)
def quotation_add(request):
    """View untuk memproses form '+ Add Quotation'."""
    if request.method == 'POST':
        form = QuotationForm(request.POST)
        if form.is_valid():
            quotation = form.save(commit=False)
            quotation.sales_person = request.user
            quotation.status = 'Sent' 
            quotation.date = timezone.now().date()
            if not quotation.quotation_number:
                quotation.save() 
                month_year = timezone.now().strftime('%Y/%m')
                quotation.quotation_number = f"Q-{month_year}/{quotation.id}"
            
            quotation.save()
            
            messages.success(request, f"Quotation {quotation.quotation_number} berhasil dibuat.")
            return redirect(f"{reverse('quotation_detail', args=[quotation.id])}?print=true")

        else:
            # Jika form tidak valid, kembali ke dashboard dan tampilkan error
            my_orders = SalesOrder.objects.filter(sales_person=request.user).select_related('sku').prefetch_related('payments').order_by('-created_at')
            my_quotations = Quotation.objects.filter(sales_person=request.user).select_related('sku').order_by('-created_at')
            
            skus_under_tech = SKU.objects.filter(assigned_technician__isnull=False).select_related('assigned_technician').order_by('assigned_technician__username')
            ready_skus_list = SKU.objects.filter(status='Ready').order_by('name')
            shop_skus_list = SKU.objects.filter(status='Shop').order_by('name')

            context = {
                'my_orders': my_orders,
                'my_quotations': my_quotations, 
                'add_order_form': SalesOrderForm(), # Form Order yang valid
                'add_quotation_form': form, # Kirim form Quotation yang tidak valid agar error terlihat
                'sidebar_skus_under_tech': skus_under_tech,
                'ready_skus_list': ready_skus_list,
                'shop_skus_list': shop_skus_list,
                'show_quotation_modal': True # Trigger modal di template
            }
            messages.error(request, "Gagal menambahkan Quotation. Cek error di bawah form.")
            return render(request, 'app/dashboards/sales_dashboard.html', context)
            
    return redirect('dashboard')

@login_required(login_url='login')
@user_passes_test(is_sales)
def quotation_detail(request, quotation_id):
    """Menampilkan detail quotation (opsional, bisa digunakan untuk konversi ke Order/Update)"""
    quotation = get_object_or_404(Quotation, id=quotation_id, sales_person=request.user)
    context = {
        'quotation': quotation,
        'valid_until_formatted': quotation.valid_until.strftime('%d %B %Y') if quotation.valid_until else '-',
    }
    return render(request, 'app/sales_quotation_detail.html', context)

@login_required(login_url='login')
@user_passes_test(is_sales)
def convert_quotation_to_order(request, quotation_id):
    """Mengkonversi Quotation menjadi SalesOrder."""
    quotation = get_object_or_404(Quotation, id=quotation_id, sales_person=request.user)
    
    if request.method == 'POST':
        # 1. Validasi Status Quotation
        if quotation.status == 'Converted':
            # Tambahkan pesan error jika sudah dikonversi
            messages.warning(request, f"Quotation ini sudah pernah dikonversi menjadi Sales Order #{quotation.converted_to_order.id}.")
            # Redirect ke Sales Order yang sudah ada
            return redirect('sales_order_detail', order_id=quotation.converted_to_order.id)

        # 2. Validasi Ketersediaan SKU
        # SalesOrder model Anda membatasi SKU hanya pada status 'Shop'
        # SKU harus Ready Shop (karena SalesOrder hanya bisa dibuat dari SKU 'Shop')
        if quotation.sku.status != 'Shop':
            messages.error(request, f"Gagal konversi. SKU ID {quotation.sku.sku_id} tidak lagi berstatus 'Ready Shop' (Status saat ini: {quotation.sku.get_status_display()}).")
            # Logika di sini penting: JIKA SKU BUKAN 'Shop', maka proses berhenti.
            return redirect('quotation_detail', quotation_id=quotation.id)

        try:
            with transaction.atomic():
                # 3. Buat SalesOrder Baru
                new_order = SalesOrder.objects.create(
                    customer_name=quotation.customer_name,
                    customer_address=quotation.customer_address,
                    customer_phone=quotation.customer_phone,
                    sku=quotation.sku,
                    price=quotation.get_total_quote, # Total quote sebagai harga jual final
                    shipping_type="Diatur Kemudian", 
                    status='Pending', # Status awal pending payment
                    sales_person=request.user
                )

                # 4. Update status Quotation
                quotation.status = 'Converted'
                quotation.converted_to_order = new_order # Tautkan Quotation ke SalesOrder
                quotation.save()

                # 5. Update Status SKU (opsional, bisa jadi 'Booked' jika harga > 0)
                # KARENA SalesOrder baru dibuat, statusnya 'Pending' (total paid = 0)
                # Namun, kita asumsikan jika Order dibuat, SKU langsung di-Booked, tapi model Anda membiarkan status SKU 'Shop'
                # Kita akan biarkan model SalesOrder yang mengurus update status SKU saat pembayaran masuk.
                
                messages.success(request, f"Quotation {quotation.quotation_number} berhasil dikonversi menjadi Sales Order #{new_order.id}. Order siap untuk proses pembayaran.")
                return redirect('sales_order_detail', order_id=new_order.id)
                
        except Exception as e:
            messages.error(request, f"Konversi gagal total (DB Error): {e}. Pastikan data SKU masih valid.")
            # print(f"ERROR SAAT KONVERSI: {e}") # Debugging
            return redirect('quotation_detail', quotation_id=quotation.id)

    # Jika bukan POST request
    return redirect('quotation_detail', quotation_id=quotation.id)


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
@user_passes_test(is_sales)
def process_shipping(request, order_id):
    """
    Mengubah status SalesOrder menjadi 'Shipped' jika sudah lunas ('Sold').
    Ini adalah aksi klik tombol "Proses Shipping".
    """
    order = get_object_or_404(SalesOrder, id=order_id, sales_person=request.user)
    
    # Memeriksa apakah order sudah lunas (diasumsikan status 'Sold' berarti lunas)
    if order.status != 'Sold':
        messages.warning(request, "Aksi dibatalkan: Order harus lunas (status 'Sold') sebelum dapat diproses pengirimannya.")
        return redirect('sales_order_detail', order_id=order.id)
        
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 1. Update status SalesOrder
                order.status = 'Shipped'
                order.shipped_at = timezone.now() # Opsi: Catat waktu pengiriman
                order.save()
                
                # 2. Update status SKU terkait
                # Asumsi: SalesOrder memiliki relasi ForeignKey ke SKU
                if order.sku:
                    order.sku.status = 'Delivering' 
                    order.sku.save()
                
            messages.success(request, f"Order {order.id} berhasil diubah status menjadi Shipped.")
        except Exception as e:
            messages.error(request, f"Gagal memproses pengiriman: {e}")
            
    return redirect('sales_order_detail', order_id=order.id)

@login_required(login_url='login')
@user_passes_test(is_sales)
def sales_receive_sku(request, movement_id):
    """
    Sales mengkonfirmasi penerimaan SKU yang sedang 'Delivering' ke Store-nya.
    """
    movement = get_object_or_404(
        MovementRequest.objects.select_related('sku_to_move', 'requested_by_store'), 
        id=movement_id, 
        status='Delivering'
    )
    
    # 1. Cek apakah Store tujuan Movement adalah Store yang ditugaskan kepada Sales ini
    try:
        sales_assignment = SalesAssignment.objects.get(sales_person=request.user)
        assigned_store = sales_assignment.assigned_store
    except SalesAssignment.DoesNotExist:
        messages.error(request, "Anda belum ditugaskan ke Store manapun.")
        return redirect('dashboard')
        
    if movement.requested_by_store != assigned_store:
        messages.error(request, "SKU ini tidak ditujukan ke Store Anda.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        receipt_file = request.FILES.get('receipt_form_file') 
        
        if not receipt_file:
            messages.error(request, "Bukti penerimaan wajib diupload.")
            return redirect('dashboard') # Kembali ke dashboard jika gagal upload
            
        try:
            with transaction.atomic():
                # 2. Update Movement Request
                movement.receipt_form = receipt_file 
                movement.status = 'Received'
                movement.received_at = timezone.now()
                movement.received_by_sales = request.user # Catat Sales yang menerima
                movement.save()

                # 3. Update SKU
                sku = movement.sku_to_move
                sku.status = 'Shop' # Status berubah menjadi Ready Store
                sku.location = 'Shop' 
                sku.current_store = assigned_store # Konfirmasi lokasi akhir di Store
                sku.save()
                
            messages.success(request, f"SKU {sku.sku_id} berhasil diterima dan kini berstatus 'Ready Store' di {assigned_store.name}.")
        except Exception as e:
            messages.error(request, f"Gagal mengkonfirmasi penerimaan: {e}")
            
        return redirect('dashboard')
    
    # Jika bukan POST, biasanya ini diakses lewat modal/form di dashboard
    # Kita tidak perlu render template, cukup redirect atau kirim JsonResponse jika diakses via AJAX
    messages.error(request, "Akses tidak sah.")
    return redirect('dashboard')

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
                'details': ( f"Pembayaran diterima <strong>Rp {amount_formatted}</strong>. <a href='{payment.proof_of_transfer.url}' target='_blank' class='fw-normal text-decoration-none text-info'> <i class='bi bi-receipt'></i> Lihat Bukti Transfer </a>")
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
    # --- 1. AMBIL DATA RACK (UNTUK MODAL) ---
    available_racks = Rack.objects.filter(status='Available', occupied_by_sku__isnull=True).order_by('rack_location')
    
    rack_grid = {}
    for rack in available_racks:
        prefix = rack.rack_location.split('-')[0]
        if prefix not in rack_grid:
            rack_grid[prefix] = []
        rack_grid[prefix].append(rack)

    if request.method == 'POST':
        # --- 2. PROSES FORM (POST) ---
        form = PurchaseOrderForm(request.POST) 
        suggested_rack_id = request.POST.get('suggested_rack') 
        
        if form.is_valid():
            po = form.save(commit=False)
            po.status = 'Pending_Approval'
            
            # Tautkan dengan Rack yang dipilih
            if suggested_rack_id:
                try:
                    # Query menggunakan ID dari hidden input
                    selected_rack = Rack.objects.get(id=suggested_rack_id, status='Available') 
                    po.suggested_rack = selected_rack 
                except Rack.DoesNotExist:
                    messages.warning(request, "Saran Rak tidak valid atau sudah terisi saat PO dibuat.")

            po.save()
            messages.success(request, f"PO {po.po_number} berhasil dibuat dan menunggu approval WM. Saran Rak: {po.suggested_rack.rack_location if po.suggested_rack else 'Tidak Ada'}")
            return redirect('dashboard')
        else:
            # Jika form tidak valid, pesan error akan muncul di bawah field
            messages.error(request, "Gagal membuat PO. Cek data yang diinput.")
    else:
        # --- 3. INISIALISASI FORM (GET) ---
        form = PurchaseOrderForm()
        
    context = {
        'form': form,
        'rack_grid': rack_grid, 
        'rack_rows': sorted(rack_grid.keys()),
    }
    return render(request, 'app/po_create.html', context)


def po_approver_required(function=None):
    """Membutuhkan user Warehouse Manager ATAU Purchasing ATAU Master Role."""
    
    # Fungsi pengecekan yang sebenarnya
    def check_user(user):
        # 1. Cek apakah dia Master Role
        if is_master_role(user):
            return True
        # 2. Cek apakah dia Warehouse Manager atau Purchasing (otorisasi standar)
        return is_warehouse_manager(user) or is_purchasing(user)

    # Terapkan user_passes_test dengan fungsi pengecekan
    actual_decorator = user_passes_test(check_user, login_url='login')
    
    if function:
        return actual_decorator(function)
    return actual_decorator

# --- Alur PO (Warehouse Manager) ---
@login_required(login_url='login')
@po_approver_required
def po_approve_list(request):
    pending_pos = PurchaseOrder.objects.filter(status='Pending_Approval').order_by('-id')
    context = {'pending_pos': pending_pos}
    return render(request, 'app/po_approve_list.html', context)

def wm_or_master_required(function=None):
    def check_user(user):
        return is_master_role(user) or is_warehouse_manager(user)
    actual_decorator = user_passes_test(check_user, login_url='login')
    if function:
        return actual_decorator(function)
    return actual_decorator

@login_required(login_url='login')
@wm_or_master_required
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

def can_view_po_detail(user):
    """Fungsi baru untuk mengizinkan WM DAN Purchasing."""
    return user.groups.filter(name__in=['Warehouse Manager', 'Purchasing']).exists()

# --- Receiving ---
@login_required(login_url='login')
@user_passes_test(can_view_po_detail)
def receiving_list(request):
    all_pos = PurchaseOrder.objects.filter(
        status__in=['Pending', 'Delivered', 'Finished']
    ).order_by('-id')
    
    context = { 'purchase_orders': all_pos }
    return render(request, 'app/receiving_list.html', context)

@login_required(login_url='login')
@user_passes_test(can_view_po_detail)
def receiving_detail(request, po_id):
    po = get_object_or_404(PurchaseOrder.objects.exclude(status__in=['Pending_Approval', 'Rejected']), id=po_id)
    
    # Inisialisasi RackSelectionForm (diisi hanya dengan rak yang available)
    rack_selection_form = RackSelectionForm(request.POST or None)

    if request.method == 'POST':
        if 'add_sku' in request.POST:
            
            # Memproses form RackSelection dan data SKU
            if rack_selection_form.is_valid():
                selected_rack = rack_selection_form.cleaned_data['available_racks']

                sku_id = request.POST.get('sku_id')
                sku_name = request.POST.get('sku_name')
                technician_id = request.POST.get('technician')
                
                if not all([sku_id, sku_name, technician_id]):
                    messages.error(request, "Gagal menambahkan SKU. Semua field wajib diisi.")
                    # Fallback agar form di render ulang dengan error rak jika ada
                    pass 
                
                try:
                    assigned_technician = User.objects.get(id=technician_id)

                    with transaction.atomic():
                        # 1. Buat SKU dan tautkan ke Rack
                        new_sku = SKU.objects.create(
                            po_number=po,
                            sku_id=sku_id,
                            name=sku_name,
                            assigned_technician=assigned_technician,
                            status='QC',
                            shelf_location=selected_rack, # << TAUTKAN RACK
                            shelved_at=timezone.now()
                        )
                        
                        # 2. Update status Rack: HIJAU -> MERAH
                        selected_rack.status = 'Used'
                        selected_rack.occupied_by_sku = new_sku
                        selected_rack.save()
                    
                    messages.success(request, f"SKU {new_sku.sku_id} diterima dan ditempatkan di rak **{selected_rack.rack_location}**.")

                    po.status = 'Delivered'
                    current_sku_count = po.skus.count()
                    if current_sku_count >= po.expected_sku_count:
                        po.status = 'Finished'
                    po.save()
                    return redirect('receiving_detail', po_id=po.id)

                except User.DoesNotExist:
                    messages.error(request, "Teknisi tidak valid.")
                except IntegrityError:
                    messages.error(request, f"SKU ID {sku_id} sudah terdaftar.")
                except Exception as e:
                     messages.error(request, f"Terjadi kesalahan saat menyimpan SKU: {e}")

            else:
                # Jika form Rack Selection GAGAL (biasanya karena tidak memilih)
                messages.error(request, "Gagal menambahkan SKU. Pastikan Anda memilih lokasi rak yang tersedia.")

        elif 'upload_dr' in request.POST:
            dr_file = request.FILES.get('delivery_receipt_file')
            if dr_file:
                po.delivery_receipt = dr_file
                po.save()
                messages.success(request, "Delivery Receipt berhasil diunggah.")
            return redirect('receiving_detail', po_id=po.id)

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
                messages.warning(request, "Notifikasi ke Purchasing telah dikirimkan.")
                return redirect('receiving_list')
            return redirect('receiving_detail', po_id=po.id)

    skus_in_po = po.skus.all()
    technicians = User.objects.filter(groups__name='Technician')
    
    context = {
        'po': po,
        'skus_in_po': skus_in_po,
        'technicians': technicians,
        # Kirim form rack ke template (ini digunakan untuk GET request dan saat POST gagal)
        'rack_selection_form': rack_selection_form 
    }
    return render(request, 'app/receiving_detail.html', context)

@login_required(login_url='login')
@user_passes_test(is_technician)
def qc_form(request, sku_id):
    sku = get_object_or_404(SKU, id=sku_id, assigned_technician=request.user)

    # 1. Kosongkan rak jika SKU berada di rak (ini adalah proses sebelum QC)
    if sku.status == 'QC' and sku.shelf_location:
        try:
            with transaction.atomic():
                rack = sku.shelf_location
                rack.occupied_by_sku = None
                rack.status = 'Available' 
                rack.save()
                sku.shelf_location = None
                sku.shelved_at = None
                sku.save()
                messages.info(request, f"Lokasi rak {rack.rack_location} berhasil dikosongkan.")
        except Exception as e:
            messages.error(request, f"Gagal mengosongkan rak: {e}")
            
    try:
        existing_form = QCForm.objects.get(sku=sku)
    except QCForm.DoesNotExist:
        existing_form = None

    # --- BARU: Ambil data Grid Rak untuk Modal (Sesuai permintaan "kursi bioskop") ---
    # Ambil semua rak, filter hanya yang available atau yang sedang ditempati
    all_racks = Rack.objects.select_related('occupied_by_sku').order_by('rack_location')
    rack_grid = {}
    
    # Kelompokkan berdasarkan prefix (misal 'A1', 'B2')
    for rack in all_racks:
        # Hanya tampilkan rack yang Available (Hijau)
        if rack.status == 'Available' or rack.occupied_by_sku == sku:
             # Asumsi format rack_location adalah A1-01. Kita ambil A1 sebagai grouping.
             prefix = rack.rack_location.split('-')[0] 
             if prefix not in rack_grid:
                 rack_grid[prefix] = []
             rack_grid[prefix].append(rack)
             
    # --- END Grid Rak preparation ---

    if request.method == 'POST':
        notes = request.POST.get('condition_notes')
        needs_spare_part = request.POST.get('needs_spare_part') == 'on'
        part_name = request.POST.get('part_name', '')
        part_qty = request.POST.get('part_qty', 1)
        qc_file = request.FILES.get('qc_document_file')
        
        # --- AMBIL ID RAK DARI FIELD HIDDEN ---
        selected_rack_id = request.POST.get('selected_rack_id') 
        
        # 2. VALIDASI RAK
        if not selected_rack_id:
            messages.error(request, "Pemilihan Rak Wajib diisi.")
            
            # Re-render dengan data grid
            context = {
                'sku': sku,
                'existing_form': existing_form,
                'rack_grid': rack_grid, # Menggunakan data grid
            }
            return render(request, 'app/qc_form.html', context)
        
        try:
            # Pastikan rak yang dipilih benar-benar Available
            selected_rack = Rack.objects.get(id=selected_rack_id, status='Available')
        except Rack.DoesNotExist:
            messages.error(request, "Rak yang dipilih tidak valid atau sudah terisi.")
            return redirect('qc_form', sku_id=sku_id)

        # 3. Proses QC Form
        qc_obj, created = QCForm.objects.get_or_create(
            sku=sku, 
            defaults={'technician': request.user, 'condition_notes': notes}
        )
        
        if not created:
            # Logika re-submit form QC yang ditolak (Logika tetap sama)
            qc_obj.condition_notes = notes
            qc_obj.is_approved_by_lead = False
            qc_obj.lead_technician_comments = None 
        if qc_file:
            qc_obj.qc_document_file = qc_file
        qc_obj.save()
        
        # 4. Proses Spare Part Request (Logika tetap sama)
        old_requests = SparePartRequest.objects.filter(
            qc_form=qc_obj, 
            status__in=['Pending', 'Rejected'] 
        )
        old_requests.delete()

        if needs_spare_part and part_name:
            SparePartRequest.objects.create(
                qc_form=qc_obj,
                part_name=part_name,
                quantity_needed=part_qty,
                status='Pending'
            )

        # 5. UPDATE RACK STATUS DAN SKU LOCATION
        with transaction.atomic():
            selected_rack.status = 'Used'
            selected_rack.occupied_by_sku = sku
            selected_rack.save()

            sku.shelf_location = selected_rack
            sku.shelved_at = timezone.now()
            sku.status = 'QC_PENDING' 
            sku.save()
        
        messages.success(request, f"Form QC disubmit. SKU {sku.sku_id} ditempatkan di rak **{selected_rack.rack_location}** dan menunggu verifikasi Lead.")

        return redirect('dashboard')

    # Kirim data rak grid ke template untuk modal
    context = {
        'sku': sku,
        'existing_form': existing_form,
        'rack_grid': rack_grid, # Menggunakan data grid
    }
    return render(request, 'app/qc_form.html', context)

@login_required(login_url='login')
@user_passes_test(is_lead_technician)
def qc_verify(request, qc_id):
    qc_form = get_object_or_404(QCForm, id=qc_id)
    sku = qc_form.sku
    # Pastikan ini hanya mengambil request yang Pending/Approved/Received, bukan yang Rejected/Issued
    part_requests = qc_form.part_requests.exclude(status__in=['Issued', 'Rejected']).all() 
    has_pending_parts = part_requests.exists()
    
    rack_grid = {}

    # --- MEMUAT DATA GRID RAK HANYA JIKA TIDAK ADA SPARE PART PENDING ---
    if not has_pending_parts:
        all_racks = Rack.objects.select_related('occupied_by_sku').order_by('rack_location')
        for rack in all_racks:
            # Tampilkan rack yang Available (Hijau)
            if rack.status == 'Available':
                 prefix = rack.rack_location.split('-')[0]
                 if prefix not in rack_grid:
                     rack_grid[prefix] = []
                 rack_grid[prefix].append(rack)

    if request.method == 'POST':
        comments = request.POST.get('comments', '')
        
        if 'approve' in request.POST:
            selected_rack_id = request.POST.get('selected_rack_id')

            qc_form.is_approved_by_lead = True
            qc_form.lead_technician_comments = comments if comments else 'QC Disetujui.'
            qc_form.managed_at = timezone.now()
            
            # Pengecekan apakah SKU memerlukan spare part setelah QC (sebelum instalasi)
            if not has_pending_parts:
                # KONDISI 1: TIDAK BUTUH PART -> SET STATUS READY & TEMPATKAN DI RAK
                
                # 1. Validasi Rack
                if not selected_rack_id:
                    # Ini seharusnya ditangani frontend, tapi sebagai fallback:
                    messages.error(request, "Persetujuan Gagal: Lokasi Rak Wajib dipilih.")
                    # Fallback rendering the view with error
                    context = {
                        'qc_form': qc_form,
                        'sku': sku,
                        'part_requests': part_requests,
                        'rack_grid': rack_grid,
                    }
                    return render(request, 'app/qc_verify.html', context)

                try:
                    selected_rack = Rack.objects.get(id=selected_rack_id, status='Available')
                except Rack.DoesNotExist:
                    messages.error(request, "Persetujuan Gagal: Rak yang dipilih tidak valid atau sudah terisi.")
                    return redirect('qc_verify', qc_id=qc_id)

                with transaction.atomic():
                    try:
                        old_rack = Rack.objects.get(occupied_by_sku=sku)
                        if old_rack.id != selected_rack.id:
                            old_rack.occupied_by_sku = None
                            old_rack.status = 'Available'
                            old_rack.save()
                            messages.warning(request, f"Rak lama {old_rack.rack_location} dikosongkan.")
                    except Rack.DoesNotExist:
                        pass

                    # B. Update SKU
                    sku.status = 'Ready'
                    sku.shelf_location = selected_rack # Set relasi ForeignKey
                    sku.shelved_at = timezone.now()
                    sku.save()

                    # C. Update Rack BARU (Ini yang menyebabkan error sebelumnya)
                    selected_rack.status = 'Used'
                    selected_rack.occupied_by_sku = sku # Set relasi OneToOne
                    selected_rack.save()
        
                    qc_form.save()
                    messages.success(request, f"QC disetujui. SKU {sku.sku_id} kini READY dan ditempatkan di rak {selected_rack.rack_location}.")

            else:
                sku.status = 'AWAITING_INSTALL' 
                sku.save()
                qc_form.save()
                messages.info(request, "QC disetujui. Permintaan Spare Part diteruskan ke Warehouse Manager (WM).")
            
            return redirect('dashboard')

        elif 'reject' in request.POST:
            # --- KELOLA REJECT ---
            if not comments:
                messages.error(request, "Komentar wajib diisi jika me-reject.")
                return redirect('qc_verify', qc_id=qc_id)
            
            qc_form.is_approved_by_lead = False
            qc_form.lead_technician_comments = comments
            qc_form.managed_at = timezone.now()
            qc_form.save()

            # Ubah status spare part request yang pending menjadi 'Rejected'
            pending_parts = SparePartRequest.objects.filter(qc_form=qc_form, status='Pending')
            for part in pending_parts:
                part.status = 'Rejected'
                part.save()

            # Reset analytics count
            technician_user = qc_form.technician
            analytics, created = TechnicianAnalytics.objects.get_or_create(technician=technician_user)
            analytics.wrong_qc_count += 1
            analytics.save()

            sku.status = 'QC'
            sku.save()
            messages.warning(request, f"QC ditolak. SKU {sku.sku_id} dikembalikan ke Teknisi.")

            return redirect('dashboard')

    # GET Request atau POST gagal (setelah validasi form non-database)
    context = {
        'qc_form': qc_form,
        'sku': sku,
        'part_requests': part_requests,
        'rack_grid': rack_grid, # Kirim data grid (mungkin kosong jika ada pending part)
    }
    return render(request, 'app/qc_verify.html', context)
@login_required(login_url='login')
@user_passes_test(is_warehouse_manager) 
def manage_sparepart(request, request_id):
    part_request = get_object_or_404(SparePartRequest, id=request_id)
    qc_form = part_request.qc_form
    sku = qc_form.sku

    # Inisialisasi
    inventory_item = part_request.issued_spare_part # Jika sudah pernah dipilih
    current_stock = inventory_item.quantity_in_stock if inventory_item else 0

    if request.method == 'POST':
        if 'issue_part' in request.POST:
            
            # 1. Ambil ID Part Inventory yang dipilih dari form POST
            issued_part_id = request.POST.get('issued_part_id')
            
            if not issued_part_id:
                messages.error(request, "Harap cari dan pilih spare part yang akan dikeluarkan dari inventaris.")
                return redirect('manage_sparepart', request_id=request_id)

            try:
                # 2. Ambil objek SparePartInventory berdasarkan ID yang dipilih WM
                inventory_item = SparePartInventory.objects.get(id=issued_part_id)
                current_stock = inventory_item.quantity_in_stock
            except SparePartInventory.DoesNotExist:
                messages.error(request, "Spare Part Inventory tidak ditemukan.")
                return redirect('manage_sparepart', request_id=request_id)
            
            
            if current_stock >= part_request.quantity_needed:
                
                # --- LOGIKA AUTO-DEDUCTION ---
                
                # 3. Kurangi Stok
                inventory_item.quantity_in_stock -= part_request.quantity_needed
                
                # Update status stok (jika habis)
                if inventory_item.quantity_in_stock == 0:
                    inventory_item.status = 'Out_Of_Stock'
                elif inventory_item.quantity_in_stock > 0 and inventory_item.status != 'Ready':
                    inventory_item.status = 'Ready'
                    
                inventory_item.save()
                
                # 4. Update Part Request (KONEKSI RELASI FOREINGKEY)
                part_request.issued_spare_part = inventory_item # <<< INI PENTING
                part_request.status = 'PENDING_LEAD_RECEIPT' 
                part_request.warehouse_manager = request.user
                part_request.managed_at = timezone.now()
                part_request.save()
                
                messages.success(request, f"Part '{inventory_item.part_name}' berhasil dikeluarkan. Menunggu konfirmasi Lead Tech.")
            else:
                messages.error(request, "Stok tidak mencukupi untuk 'Issue Part'. Harap cek kembali inventaris atau Setujui Pembelian.")

        elif 'approve_buy' in request.POST:
            part_request.status = 'Approved_Buy'
            part_request.warehouse_manager = request.user
            part_request.managed_at = timezone.now()
            part_request.save()
            messages.info(request, "Request pembelian telah diteruskan ke Purchasing.")

        return redirect('dashboard')
    try:
        display_item = SparePartInventory.objects.filter(part_name__iexact=part_request.part_name).first()
        current_stock = display_item.quantity_in_stock if display_item else 0
    except Exception:
        current_stock = 0


    context = {
        'part_request': part_request,
        'sku': sku,
        'current_stock': current_stock,
        'inventory_item': display_item # Kirim item yang dicari berdasarkan nama
    }
    return render(request, 'app/manage_sparepart.html', context)


@login_required(login_url='login')
@user_passes_test(is_warehouse_manager) 
def movement_process(request):
    
    if request.method == 'POST':
        # --- Hanya proses 'create_movement' ---
        if 'create_movement' in request.POST:
            form = MovementRequestForm(request.POST, request.FILES)
            if form.is_valid():
                movement = form.save(commit=False)
                sku_to_move = movement.sku_to_move
                
                # Cek jika SKU sudah Delivering
                if sku_to_move.status in ['Delivering', 'Shop', 'Booked', 'Sold', 'Shipped', 'Completed']:
                    messages.error(request, f"SKU {sku_to_move.sku_id} tidak bisa dikirim. Status saat ini: {sku_to_move.get_status_display()}")
                    return redirect('movement_process')

                movement.status = 'Delivering'
                movement.save()

                sku_to_move.status = 'Delivering'
                sku_to_move.location = 'Shop' # Update lokasi sementara
                sku_to_move.current_store = movement.requested_by_store # Set Store Tujuan
                sku_to_move.save()

                messages.success(request, f"Pengiriman SKU {sku_to_move.sku_id} ke {movement.requested_by_store.name} berhasil dibuat. Menunggu penerimaan Sales.")
            else:
                messages.error(request, "Gagal membuat pengiriman. Cek form di bawah.")

        return redirect('movement_process')

    # --- Tampilan GET Request ---
    
    # Data untuk form (hanya SKU yang siap pindah)
    # Queryset dipindahkan ke MovementRequestForm
    form = MovementRequestForm() 
    
    # Tampilkan Movement yang statusnya 'Delivering'
    movements_in_progress = MovementRequest.objects.filter(status='Delivering').select_related('sku_to_move', 'requested_by_store')

    # Data Store & Sales untuk label di template (Optional, tapi membantu)
    stores_with_sales = SalesAssignment.objects.select_related('sales_person', 'assigned_store').all()

    context = {
        'movement_form': form, # Menggunakan form yang baru
        'movements_in_progress': movements_in_progress,
        'stores_with_sales': stores_with_sales,
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

    rack_form = RackSelectionForm() # Instansiasi untuk dikirim ke modal

    is_pending_final_check = sku.status == 'PENDING_FINAL_CHECK'
    
    if request.method == 'POST':
        comments = request.POST.get('comments', '')
        
        # --- KELOLA APPROVE ---
        if 'approve' in request.POST:
            # 1. AMBIL ID RAK & SKU PART LAMA DARI FIELD HIDDEN
            selected_rack_id = request.POST.get('selected_rack_id') 
            lead_assigned_sku = request.POST.get('lead_assigned_sku', '') # Dari field hidden di modal
            
            # 2. Validasi Rak (Harusnya sudah dicek di frontend, tapi perlu cek di backend juga)
            if is_pending_final_check and not selected_rack_id:
                messages.error(request, "APPROVAL GAGAL: Harap pilih lokasi rak yang tersedia.")
                # Re-render form dengan error
                context = {
                    'qc_form': qc_form,
                    'sku': sku,
                    'returned_part': returned_part,
                    'rack_form': RackSelectionForm(request.POST), # Re-Instantiate dengan data POST
                    'is_pending_final_check': is_pending_final_check,
                }
                return render(request, 'app/final_check.html', context)
            
            selected_rack = None
            if selected_rack_id:
                try:
                    selected_rack = Rack.objects.get(id=selected_rack_id)
                except Rack.DoesNotExist:
                    messages.error(request, "Rak yang dipilih tidak valid.")
                    return redirect('final_check', qc_id=qc_id)

            # 3. Validasi SKU Part Lama (Jika ada part yang dikembalikan)
            if returned_part and not lead_assigned_sku:
                messages.error(request, "APPROVAL GAGAL: Anda wajib mengisi Nomor SKU untuk sparepart lama yang dikembalikan.")
                # Re-render form dengan error
                context = {
                    'qc_form': qc_form,
                    'sku': sku,
                    'returned_part': returned_part,
                    'rack_form': RackSelectionForm(request.POST), # Re-Instantiate dengan data POST
                    'is_pending_final_check': is_pending_final_check,
                }
                return render(request, 'app/final_check.html', context)
            
            # --- START DATABASE TRANSACTION ---
            try:
                with transaction.atomic():
                    qc_form.final_lead_comments = comments if comments else "Instalasi disetujui."
                    qc_form.final_approval_at = timezone.now()
                    qc_form.final_managed_at = timezone.now()
                    qc_form.save()
                    
                    # 4. Update SKU Status
                    sku.status = 'Ready'
                    
                    # 5. Logika Penempatan Rack (Hijau -> Merah)
                    if selected_rack:
                        # Jika SKU sebelumnya ada di rak manapun, lepaskan dulu
                        if sku.shelf_location:
                            old_rack = sku.shelf_location
                            old_rack.occupied_by_sku = None
                            old_rack.status = 'Available'
                            old_rack.save()

                        # Set rak baru
                        selected_rack.status = 'Used'
                        selected_rack.occupied_by_sku = sku
                        selected_rack.save()
                        
                        sku.shelf_location = selected_rack
                        sku.shelved_at = timezone.now()
                        messages.success(request, f"Instalasi SKU {sku.sku_id} disetujui. SKU sekarang 'Ready' dan ditempatkan di rak **{selected_rack.rack_location}**.")
                    else:
                        messages.success(request, f"Instalasi SKU {sku.sku_id} disetujui. SKU sekarang 'Ready'.")
                        
                    sku.save()
                    
                    # 6. Logika Part Lama (Jika ada)
                    if returned_part:
                        returned_part.status = 'Approved'
                        returned_part.lead_assigned_sku = lead_assigned_sku
                        returned_part.approved_by_lead = request.user
                        returned_part.managed_at = timezone.now()
                        returned_part.save()
                        
                        # Update/Create Inventory WM (Logika tetap sama)
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
                            part_inventory.quantity_in_stock += 1
                            part_inventory.status = 'Ready'
                            part_inventory.origin = 'RETURN'
                            part_inventory.save()
                            
                    return redirect('dashboard')
            except Exception as e:
                messages.error(request, f"Gagal memproses approval SKU: {e}")
                return redirect('final_check', qc_id=qc_id)

        # --- KELOLA REJECT ---
        elif 'reject' in request.POST:
            if not comments:
                messages.error(request, "Komentar wajib diisi jika me-reject.")
                return redirect('final_check', qc_id=qc_id)
            
            qc_form.final_lead_comments = comments
            qc_form.final_approval_at = None 
            qc_form.final_managed_at = timezone.now()
            qc_form.save()

            # Hapus SKU dari rak jika ada
            if sku.shelf_location:
                try:
                    with transaction.atomic():
                        rack = sku.shelf_location
                        rack.occupied_by_sku = None
                        rack.status = 'Available' 
                        rack.save()
                        sku.shelf_location = None
                        sku.shelved_at = None
                        messages.warning(request, f"Rak {rack.rack_location} dikosongkan.")
                except Exception as e:
                    messages.error(request, f"Gagal mengosongkan rak: {e}")
            
            sku.status = 'AWAITING_INSTALL'
            sku.save()
            
            if returned_part:
                returned_part.status = 'Rejected' 
                returned_part.managed_at = timezone.now()
                returned_part.save()
                
            messages.warning(request, f"Instalasi SKU {sku.sku_id} ditolak dan dikembalikan ke teknisi.")
            return redirect('dashboard')

    # GET Request atau POST gagal (setelah validasi form non-database)
    context = {
        'qc_form': qc_form,
        'sku': sku,
        'returned_part': returned_part,
        'rack_form': rack_form, # Kirim form rak untuk modal
        'is_pending_final_check': is_pending_final_check,
        'installation_photos_before': InstallationPhoto.objects.filter(qc_form=qc_form, photo_type='before'),
        'installation_photos_after': InstallationPhoto.objects.filter(qc_form=qc_form, photo_type='after'),
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
        ).order_by('-quantity_in_stock')[:10]
        
        for part in parts:
            results.append({
                'id': part.id, 
                'name': part.part_name,
                'stock': part.quantity_in_stock,
                'location': part.location or '-',
                'sku_part': part.part_sku or '-',
                'supplier': part.primary_supplier or '-'
            })
            
    return JsonResponse(results, safe=False)

def get_logo_path():
    """Mencoba menemukan logo di direktori statis."""
    # Pastikan file logo Anda ada di direktori static: 'app/images/bringco.png'
    static_path = find_static('app/images/bringco.png')
    if static_path and os.path.exists(static_path):
        return static_path
        
    # Fallback jika tidak ditemukan
    try:
        if settings.STATICFILES_DIRS:
            logo_path_manual = os.path.join(settings.STATICFILES_DIRS[0], 'app/images/bringco.png')
            if os.path.exists(logo_path_manual):
                return logo_path_manual
    except (AttributeError, IndexError):
        pass

    return None

@login_required(login_url='login')
@user_passes_test(is_sales)
def print_order_label(request, order_id):
    """
    Menghasilkan label/faktur mini dalam format PDF ukuran 10x15 cm.
    Mengatasi masalah alamat yang terpotong dan harga yang bertabrakan, 
    serta memastikan layout terstruktur dan menarik.
    """
    try:
        order = get_object_or_404(SalesOrder, id=order_id, sales_person=request.user)
    except SalesOrder.DoesNotExist:
        # Menghandle kasus jika order tidak ditemukan atau sales_person tidak cocok
        return HttpResponse("Order not found or access denied.", status=404)

    # --- Pengaturan Ukuran Halaman ---
    LABEL_WIDTH = 10 * cm
    LABEL_HEIGHT = 15 * cm
    
    # --- Persiapan Canvas PDF ---
    response = HttpResponse(content_type='application/pdf')
    filename = f'Order_Label_{order.id}_{order.customer_name.replace(" ", "_")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    p = canvas.Canvas(response, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
    
    # --- Margin dan Posisi Awal ---
    x_margin = 0.5 * cm
    # Lebar efektif untuk konten
    content_width = LABEL_WIDTH - 2 * x_margin
    # Posisi Y awal (dari atas)
    y_position = LABEL_HEIGHT - x_margin
    LINE_HEIGHT = 0.4 * cm # Jarak antar baris standar
    
    # Lebar per kolom untuk alamat (4.5 cm)
    COL_WIDTH = 4.5 * cm
    MAX_ADDR_CHARS = int(COL_WIDTH / (p.stringWidth('W', 'Helvetica', 9) / 1.0))
    ADDR_LINE_SPACING = 0.35 * cm # Spasi rapat untuk alamat

    # --- Bagian 1: Header (Logo & Judul) 📦 ---
    p.setLineWidth(1)
    
    logo_path = get_logo_path()
    y_header_start = y_position
    
    if logo_path:
        try:
            logo = ImageReader(logo_path)
            logo_width = 2.5 * cm
            aspect_ratio = logo.getSize()[1] / logo.getSize()[0]
            logo_height = logo_width * aspect_ratio
            
            # Draw Logo (Kiri)
            p.drawImage(logo, x_margin, y_header_start - logo_height, width=logo_width, height=logo_height)
            
            # Draw Judul (Kanan)
            p.setFont('Helvetica-Bold', 14)
            p.drawRightString(LABEL_WIDTH - x_margin, y_header_start - 0.7 * cm, "INVOICE PENGIRIMAN")
            p.setFont('Helvetica', 9)
            p.drawRightString(LABEL_WIDTH - x_margin, y_header_start - 1.2 * cm, "BringCo - Official Shipping Label")
            
            y_position = y_header_start - max(logo_height, 1.5 * cm) - 0.2 * cm
            
        except Exception:
            # Jika logo gagal dimuat
            p.setFont('Helvetica-Bold', 14)
            p.drawString(x_margin, y_position, "INVOICE/LABEL PENGIRIMAN")
            y_position -= 0.6 * cm
            p.setFont('Helvetica', 9)
            p.drawString(x_margin, y_position, "BringCo - Official Shipping Label")
            y_position -= 0.5 * cm
    else:
        # Jika tidak ada path logo
        p.setFont('Helvetica-Bold', 14)
        p.drawString(x_margin, y_position, "INVOICE/LABEL PENGIRIMAN")
        y_position -= 0.6 * cm
        p.setFont('Helvetica', 9)
        p.drawString(x_margin, y_position, "BringCo - Official Shipping Label")
        y_position -= 0.5 * cm
            
    # Garis pemisah Header
    p.line(x_margin, y_position, LABEL_WIDTH - x_margin, y_position)
    y_position -= 0.4 * cm
    
    # --- Bagian 2: Informasi Umum Order (2 Kolom) 📅 ---
    col1_x = x_margin
    col2_x = LABEL_WIDTH / 2.0
    
    p.setFont('Helvetica', 9)
    
    # Kiri: Order ID & Tanggal
    p.drawString(col1_x, y_position, f"Order ID:")
    p.setFont('Helvetica-Bold', 9)
    p.drawString(col1_x + 1.8 * cm, y_position, f"{order.id}") 
    p.setFont('Helvetica', 9) # Reset
    y_position -= LINE_HEIGHT
    
    p.drawString(col1_x, y_position, f"Tgl Order:")
    p.drawString(col1_x + 1.8 * cm, y_position, f"{order.created_at.strftime('%d-%m-%Y')}")
    
    # Kanan: Pengiriman & Status
    temp_y = y_position + LINE_HEIGHT # Atur agar sejajar dengan Tgl Order
    
    p.drawString(col2_x, temp_y, f"Pengiriman:")
    p.setFont('Helvetica-Bold', 9)
    p.drawString(col2_x + 2.0 * cm, temp_y, f"{order.shipping_type or '-'}") 
    temp_y -= LINE_HEIGHT
    p.setFont('Helvetica', 9) # Reset
    
    p.drawString(col2_x, temp_y, f"Status:")
    p.drawString(col2_x + 2.0 * cm, temp_y, f"{order.get_status_display()}")
    
    # Ambil posisi Y terendah dan beri jarak
    y_position = min(y_position, temp_y) - 0.4 * cm
    p.setLineWidth(2) # Garis lebih tebal untuk pemisah utama
    p.line(x_margin, y_position, LABEL_WIDTH - x_margin, y_position)
    p.setLineWidth(1) # Reset line width
    y_position -= 0.5 * cm
    
    # --- Bagian 3: Data Customer & Alamat (Area Utama) 👤🏠 ---
    current_y = y_position
    col1_x = x_margin
    col2_x = LABEL_WIDTH / 2.0

    # Judul Kiri (PENERIMA)
    p.setFont('Helvetica-Bold', 10)
    p.setFillColorRGB(0.1, 0.1, 0.5) # Warna biru gelap
    p.drawString(col1_x, current_y, "PENERIMA:")
    
    # Judul Kanan (PENGIRIM)
    p.setFillColorRGB(0.5, 0.1, 0.1) # Warna merah gelap
    p.drawString(col2_x, current_y, "PENGIRIM:")
    p.setFillColorRGB(0, 0, 0) # Reset warna ke hitam
    current_y -= 0.5 * cm
    
    # --- Kolom PENERIMA ---
    current_y_col1 = current_y
    p.setFont('Helvetica', 9)
    
    # Nama Penerima (Bold)
    p.drawString(col1_x, current_y_col1, f"Nama: ") 
    p.setFont('Helvetica-Bold', 9)
    p.drawString(col1_x + 1.2 * cm, current_y_col1, f"{order.customer_name}")
    p.setFont('Helvetica', 9) # Reset
    current_y_col1 -= LINE_HEIGHT
    
    # Telp Penerima
    p.drawString(col1_x, current_y_col1, f"Telp: {order.customer_phone}")
    current_y_col1 -= 0.5 * cm
    
    # Alamat Penerima (Wrapping)
    p.setFont('Helvetica-Bold', 9)
    p.drawString(col1_x, current_y_col1, "Alamat:")
    current_y_col1 -= ADDR_LINE_SPACING
    
    p.setFont('Helvetica', 9)
    textobject_addr = p.beginText(col1_x, current_y_col1)
    textobject_addr.setFont('Helvetica', 9)
    
    wrapped_address = textwrap.wrap(order.customer_address, width=MAX_ADDR_CHARS)
    
    for line in wrapped_address:
        textobject_addr.textLine(line)
        current_y_col1 -= ADDR_LINE_SPACING
        
    p.drawText(textobject_addr)
    # Tambahkan sedikit jarak setelah alamat
    current_y_col1 -= 0.1 * cm 
    
    # --- Kolom PENGIRIM ---
    current_y_col2 = current_y
    p.setFont('Helvetica', 9)
    
    # Nama Pengirim
    p.drawString(col2_x, current_y_col2, f"Nama: BringCo")
    current_y_col2 -= LINE_HEIGHT
    
    # Telp Pengirim
    p.drawString(col2_x, current_y_col2, f"Telp: +62-812-1414-4787")
    current_y_col2 -= 0.5 * cm
    
    # Alamat Pengirim (Wrapping)
    p.setFont('Helvetica-Bold', 9)
    p.drawString(col2_x, current_y_col2, "Alamat:")
    current_y_col2 -= ADDR_LINE_SPACING
    
    p.setFont('Helvetica', 9)
    sender_address_text = "Jl. Tebet Timur Dalam II No.7 Kec. Tebet, Jakarta Selatan 12820"
    
    textobject_addr_sender = p.beginText(col2_x, current_y_col2)
    textobject_addr_sender.setFont('Helvetica', 9)
    
    wrapped_sender_address = textwrap.wrap(sender_address_text, width=MAX_ADDR_CHARS) 
    
    for line in wrapped_sender_address:
        textobject_addr_sender.textLine(line)
        current_y_col2 -= ADDR_LINE_SPACING
        
    p.drawText(textobject_addr_sender)
    current_y_col2 -= 0.1 * cm 

    # Tentukan batas bawah area alamat (Ambil posisi Y terendah)
    y_position = min(current_y_col1, current_y_col2) - 0.4 * cm
    p.setLineWidth(2) # Garis lebih tebal untuk pemisah utama
    p.line(x_margin, y_position, LABEL_WIDTH - x_margin, y_position)
    p.setLineWidth(1) # Reset line width
    y_position -= 0.5 * cm
    
    # --- Bagian 4: Detail Barang & Harga (Faktur Mini) 💵 ---
    
    # Kiri: SKU ID & Nama Barang (Jika ada)
    p.setFont('Helvetica-Bold', 10)
    p.drawString(x_margin, y_position, "SKU ID & Nama Barang:")
    y_position -= 0.5 * cm
    
    p.setFont('Helvetica', 9)
    
    # SKU ID
    p.drawString(x_margin, y_position, f"SKU ID:")
    p.setFont('Helvetica-Bold', 10) # Lebih besar untuk SKU ID
    p.drawString(x_margin + 2.0 * cm, y_position, f"{order.sku.sku_id if order.sku else 'N/A'}") 
    p.setFont('Helvetica', 9) # Reset
    y_position -= LINE_HEIGHT

    # Nama Barang
    p.drawString(x_margin, y_position, f"Barang:")
    p.drawString(x_margin + 2.0 * cm, y_position, f"{order.sku.name if order.sku and order.sku.name else 'Detail Barang'}") 
    
    # Kanan: Harga (Stacked & Menarik)
    harga_formatted = intcomma(order.price)
    temp_y = y_position + LINE_HEIGHT # Sejajar dengan SKU ID
    
    # Baris 1: Label "TOTAL HARGA JUAL" (Right Aligned, Highlighted)
    p.setFont('Helvetica-Bold', 9)
    p.setFillColorRGB(0.5, 0.0, 0.5) # Warna ungu/magenta
    p.drawRightString(LABEL_WIDTH - x_margin, temp_y, f"TOTAL HARGA JUAL:")
    
    temp_y -= LINE_HEIGHT
    
    # Baris 2: Nilai Harga (Bold, Lebih Besar, Right Aligned)
    p.setFont('Helvetica-Bold', 12)
    p.setFillColorRGB(0.0, 0.5, 0.0) # Warna hijau
    p.drawRightString(LABEL_WIDTH - x_margin, temp_y, f"Rp {harga_formatted}")
    
    p.setFont('Helvetica', 9) # Reset
    p.setFillColorRGB(0, 0, 0) # Reset warna ke hitam
    
    # Tentukan posisi Y terendah
    y_position = min(y_position, temp_y) - 0.5 * cm
    
    p.line(x_margin, y_position, LABEL_WIDTH - x_margin, y_position)
    y_position -= 0.3 * cm
    
    # --- Bagian 5: Footer 📝 ---
    p.setFont('Helvetica-Oblique', 7)
    
    # Kiri: Pesan Terima Kasih
    p.drawString(x_margin, y_position, "Terima kasih telah berbelanja.")
    
    # Kanan: Info Cetak
    p.drawRightString(LABEL_WIDTH - x_margin, y_position, 
                      f"Dicetak oleh Sales: {request.user.username} | {timezone.now().strftime('%d/%m/%Y %H:%M')}")
    
    p.showPage()
    p.save()
    return response

# --- VIEW: PRINT INVOICE A4 ---

def draw_header(p, width, margin_x, header_start_y, company_info_x, order):
    """Menggambar logo, info perusahaan, dan judul invoice."""
    
    # 1. Logo (Kiri)
    logo_x = margin_x
    logo_y = header_start_y - 1.5 * cm
    
    logo_path = get_logo_path()
    if logo_path:
        try:
            logo = ImageReader(logo_path)
            p.drawImage(logo, logo_x, logo_y, width=3.5*cm, height=3.5*cm, mask='auto')
        except Exception:
            p.setFont('Helvetica-Bold', 12)
            p.drawString(logo_x, logo_y + 0.5*cm, "BringCO (Logo Error)")
    else:
        p.setFont('Helvetica-Bold', 14)
        p.drawString(logo_x, logo_y + 0.5*cm, "BRINGCO")

    # 2. Info Perusahaan (Detail)
    company_y = logo_y + 1.5 * cm
    p.setFont('Helvetica-Bold', 10)
    p.drawString(company_info_x, company_y, "BRINGCO HEADQUARTERS")
    company_y -= 0.4 * cm
    p.setFont('Helvetica', 8)
    p.drawString(company_info_x, company_y, "Jl. Tebet Timur Dalam II No.7 Kec. Tebet, Jakarta Selatan 12820")
    company_y -= 0.4 * cm
    p.drawString(company_info_x, company_y, "Telp: +62-812-1414-4787 | Email: bringco.hq@gmail.com")

    # 3. Judul Invoice & Nomor (Kanan)
    p.setFont('Helvetica-Bold', 24)
    p.setFillColor(colors.HexColor('#004d99')) # Darker Corporate Blue
    p.drawRightString(width - margin_x, header_start_y, "INVOICE")
    p.setFillColor(colors.black)
    
    p.setFont('Helvetica-Bold', 10)
    p.drawRightString(width - margin_x, header_start_y - 1.0 * cm, "INVOICE NO:")
    p.setFont('Helvetica', 10)
    p.drawRightString(width - margin_x, header_start_y - 1.4 * cm, f"INV/{order.created_at.strftime('%Y%m')}/{order.id}")
    
    return header_start_y - 3.5 * cm # Posisi Y setelah header

def draw_transaction_info(p, order, request_user, width, margin_x, current_y):
    """Menggambar detail pelanggan dan info transaksi."""
    
    LINE_HEIGHT = 0.45 * cm
    
    # --- POSISI X UNTUK PELURUSAN TITIK DUA ---
    COLON_X_BILL_TO = margin_x + 2.5 * cm # Cukup ruang untuk "Telepon"
    RIGHT_COL_X = width / 2 + 1 * cm
    COLON_X_RIGHT = RIGHT_COL_X + 3.0 * cm # Cukup ruang untuk "Sales Person" (3.0 cm)

    # Kolom Kiri (Bill To)
    current_y_temp = current_y
    p.setFont('Helvetica-Bold', 11)
    p.drawString(margin_x, current_y_temp, "BILL TO:")
    current_y_temp -= 0.6 * cm
    
    p.setFont('Helvetica', 10)
    
    # Nama
    p.drawString(margin_x, current_y_temp, "Nama")
    p.drawString(COLON_X_BILL_TO, current_y_temp, ":")
    p.drawString(COLON_X_BILL_TO + 0.2 * cm, current_y_temp, f"{order.customer_name}")
    current_y_temp -= LINE_HEIGHT
    
    # Telepon
    p.drawString(margin_x, current_y_temp, "Telepon")
    p.drawString(COLON_X_BILL_TO, current_y_temp, ":")
    p.drawString(COLON_X_BILL_TO + 0.2 * cm, current_y_temp, f"{order.customer_phone}")
    current_y_temp -= LINE_HEIGHT
    
    # Alamat
    p.drawString(margin_x, current_y_temp, "Alamat")
    p.drawString(COLON_X_BILL_TO, current_y_temp, ":")
    
    # Alamat (wrapping) - Lebar efektif kolom kiri sekitar 7 cm.
    ADDRESS_WRAP_WIDTH = 40 # Estimasi 40 karakter agar tidak bertabrakan dengan kolom kanan
    address_x = COLON_X_BILL_TO + 0.2 * cm
    textobject_addr = p.beginText(address_x, current_y_temp)
    textobject_addr.setFont('Helvetica', 10)
    
    wrapped_addr = textwrap.wrap(order.customer_address, width=ADDRESS_WRAP_WIDTH) 
    
    temp_y_addr = current_y_temp
    addr_line_spacing = 0.4 * cm 
    for line in wrapped_addr:
        textobject_addr.textLine(line)
        temp_y_addr -= addr_line_spacing
        
    p.drawText(textobject_addr)
    current_y_temp = temp_y_addr # Update posisi Y kolom kiri

    # Kolom Kanan (Transaction Info)
    current_y_right = current_y
    
    p.setFont('Helvetica-Bold', 11)
    p.drawString(RIGHT_COL_X, current_y_right, "TRANSACTION INFO:")
    current_y_right -= 0.6 * cm

    p.setFont('Helvetica', 10)
    
    # Tanggal Invoice
    p.drawString(RIGHT_COL_X, current_y_right, "Tanggal Invoice")
    p.drawString(COLON_X_RIGHT, current_y_right, ":")
    p.drawRightString(width - margin_x, current_y_right, f"{order.created_at.strftime('%d %B %Y')}")
    current_y_right -= LINE_HEIGHT
    
    # Sales Person
    p.drawString(RIGHT_COL_X, current_y_right, "Sales Person")
    p.drawString(COLON_X_RIGHT, current_y_right, ":")
    p.drawRightString(width - margin_x, current_y_right, f"{request_user.username}")
    current_y_right -= LINE_HEIGHT

    # Pengiriman
    p.drawString(RIGHT_COL_X, current_y_right, "Pengiriman")
    p.drawString(COLON_X_RIGHT, current_y_right, ":")
    p.drawRightString(width - margin_x, current_y_right, f"{order.shipping_type or 'N/A'}")
    
    # Kembalikan posisi Y terendah untuk memulai tabel
    return min(current_y_temp, current_y_right)

def create_item_table(order, width, margin_x, quantity, total_price_int):
    """Membuat objek tabel detail item."""
    content_width = width - 2 * margin_x
    
    table_data = [
        ["NO.", "DESCRIPTION (SKU ID)", "QTY", "UNIT PRICE (RP)", "LINE TOTAL (RP)"],
        [
            "1.",
            f"{order.sku.name}\n(ID: {order.sku.sku_id})",
            f"{quantity}",
            f"{intcomma(order.price)}",
            f"{intcomma(total_price_int)}"
        ]
    ]
    
    # Penyesuaian lebar kolom agar lebih proporsional
    col_widths = [
        0.8 * cm,                   # NO.
        content_width * 0.48,       # DESCRIPTION (Lebar diperbesar)
        1.5 * cm,                   # QTY
        content_width * 0.20,       # UNIT PRICE
        content_width * 0.20,       # LINE TOTAL
    ]
    
    item_table = Table(table_data, colWidths=col_widths)
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#004d99')), # Darker Blue
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('ALIGN', (3, 1), (4, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ])
    item_table.setStyle(table_style)
    return item_table

# --- FUNGSI UTAMA YANG DIREVISI ---

@login_required(login_url='login')
@user_passes_test(is_sales)
def print_invoice_a4(request, order_id):
    """
    Menghasilkan Invoice penjualan dalam format PDF A4 yang profesional.
    Struktur kode diperbaiki dan posisi X diperhitungkan secara akurat.
    """
    try:
        order = get_object_or_404(SalesOrder, id=order_id, sales_person=request.user)
    except Exception:
        return HttpResponse("Order not found or access denied.", status=404)

    # --- Setup Canvas ---
    response = HttpResponse(content_type='application/pdf')
    filename = f"INVOICE_ORDER_{order.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'    

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin_x = 2 * cm
    current_y = height - 2 * cm
    
    # --- ZONA 1: HEADER PERUSAHAAN & JUDUL INVOICE ---
    header_start_y = current_y
    company_info_x = margin_x + 5 * cm
    
    current_y = draw_header(p, width, margin_x, header_start_y, company_info_x, order)
    
    p.line(margin_x, current_y, width - margin_x, current_y) # Garis Penuh
    
    # --- ZONA 2: DETAIL PELANGGAN & TANGGAL ---
    current_y -= 0.8 * cm
    
    current_y = draw_transaction_info(p, order, request.user, width, margin_x, current_y)
    
    p.line(margin_x, current_y - 0.5 * cm, width - margin_x, current_y - 0.5 * cm) # Garis Penuh
    current_y -= 1.0 * cm
    
    # --- ZONA 3: DETAIL ITEM TRANSAKSI ---
    
    quantity = 1
    total_price_int = order.price * quantity
    shipping_cost = 0 
    
    item_table = create_item_table(order, width, margin_x, quantity, total_price_int)
    
    # Hitung tinggi tabel
    table_height = item_table.wrapOn(p, width, height)[1] 
    current_y -= table_height 

    # Gambar Tabel
    item_table.drawOn(p, margin_x, current_y)
    
    current_y -= 0.5 * cm
    
    # --- ZONA 4: RINGKASAN KEUANGAN ---
    SUMMARY_TABLE_WIDTH = (width - 2 * margin_x) * 0.45 # Diperbesar sedikit
    SUMMARY_COL_WIDTHS = [SUMMARY_TABLE_WIDTH * 0.60, SUMMARY_TABLE_WIDTH * 0.40] 
    summary_x = width - margin_x - SUMMARY_TABLE_WIDTH
    
    total_tagihan = total_price_int + shipping_cost
    sisa_tagihan = order.get_remaining_balance() # Asumsi fungsi ini mengembalikan int/float
    
    summary_data = [
        ["SUBTOTAL", f"Rp {intcomma(total_price_int)}"],
        ["Biaya Pengiriman", f"Rp {intcomma(shipping_cost)}"],
        ["TOTAL TAGIHAN", f"Rp {intcomma(total_tagihan)}"],
        ["SUDAH TERBAYAR", f"Rp {intcomma(order.get_total_paid())}"],
        ["SISA TAGIHAN", f"Rp {intcomma(sisa_tagihan)}"],
    ]
    
    summary_table = Table(summary_data, colWidths=SUMMARY_COL_WIDTHS)
    summary_style = TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'), 
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'), 
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'), # Total Tagihan Bold
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'), # Sisa Tagihan Bold
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (1, 2), (1, 2), colors.darkgreen),
        ('TEXTCOLOR', (1, 4), (1, 4), colors.red),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#E6FFE6')), # Total Tagihan Highlight
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#FFF2F2')), # Sisa Tagihan Highlight
        ('RIGHTPADDING', (0, 0), (0, -1), 5), 
    ])
    summary_table.setStyle(summary_style)
    summary_height = summary_table.wrapOn(p, width, height)[1]
    
    # Gambar Tabel Summary (Posisikan di pojok kanan bawah dari ZONA 3)
    summary_table.drawOn(p, summary_x, current_y - summary_height)
    
    # Tentukan posisi Y final (karena catatan mungkin lebih rendah)
    final_y_notes = current_y - summary_height - 0.5 * cm
    
    # --- ZONA 5: TERMS AND SIGNATURE ---
    
    # Catatan Tambahan (Kiri)
    current_y_notes = current_y 
    p.setFont('Helvetica-Bold', 10)
    p.drawString(margin_x, current_y_notes, "CATATAN:")
    current_y_notes -= 0.4 * cm
    p.setFont('Helvetica', 9)
    p.drawString(margin_x, current_y_notes, f"Sisa tagihan **Rp {intcomma(sisa_tagihan)}** jatuh tempo dalam 7 hari.")
    current_y_notes -= 0.4 * cm
    p.drawString(margin_x, current_y_notes, "Pembayaran dapat ditransfer ke Bank XYZ, A/N BRINGCO.")
    
    # Ambil posisi Y terendah dari notes
    current_y_notes = min(current_y_notes, final_y_notes)
    
    # Tanda Tangan (Kanan Bawah)
    ttd_x = width - margin_x - 5 * cm
    
    # Y position untuk tanda tangan (misal 3.5 cm dari bawah)
    final_y_pos = 4 * cm 
    
    # Header Tanda Tangan
    p.setFont('Helvetica-Bold', 10)
    p.drawCentredString(ttd_x + 2.5 * cm, final_y_pos, "Hormat Kami,")
    
    # Garis Tanda Tangan
    p.line(ttd_x, final_y_pos - 1 * cm, ttd_x + 5 * cm, final_y_pos - 1 * cm)
    
    # Nama dan Jabatan
    p.setFont('Helvetica-Bold', 10)
    # Gunakan nama lengkap jika ada, fallback ke username
    signer_name = request.user.get_full_name() or request.user.username
    p.drawCentredString(ttd_x + 2.5 * cm, final_y_pos - 1.5 * cm, f"{signer_name}")
    p.setFont('Helvetica', 9)
    p.drawCentredString(ttd_x + 2.5 * cm, final_y_pos - 1.9 * cm, "Sales Representative")
    
    # --- Footer ---
    p.setFont('Helvetica-Oblique', 8)
    p.drawCentredString(width / 2, 1.5 * cm, "Terima kasih atas kepercayaan Anda.")
    
    p.showPage()
    p.save()
    return response

@login_required(login_url='login')
@user_passes_test(is_sales)
def print_quotation_a4(request, quotation_id):
    # 1. Fetch Data
    try:
        quotation = get_object_or_404(Quotation, id=quotation_id, sales_person=request.user)
    except Exception:
        return HttpResponse("Quotation not found or access denied.", status=404)

    # 2. Setup Canvas
    response = HttpResponse(content_type='application/pdf')
    filename = f"QUOTATION_{quotation.quotation_number or quotation.id}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin_x = 2 * cm
    
    # --- ZONA 1: HEADER (LOGO & JUDUL) 🏷️ ---
    
    # Ukuran Logo dan Posisi
    LOGO_WIDTH = 5.0 * cm
    LOGO_HEIGHT = 3.8 * cm  
    # Posisi Y untuk bagian bawah logo
    LOGO_Y_BOTTOM = height - margin_x - LOGO_HEIGHT
    
    logo_path = get_logo_path()
    
    # 1. Gambar Logo (Pojok Kiri Atas)
    if logo_path:
        try:
            p.drawImage(logo_path, margin_x, LOGO_Y_BOTTOM, 
                        width=LOGO_WIDTH, height=LOGO_HEIGHT, 
                        preserveAspectRatio=True)
        except Exception:
            p.setFont('Helvetica-Bold', 8)
            p.setFillColor(colors.red)
            p.drawString(margin_x, height - margin_x - 0.5 * cm, "LOGO ERROR!")
    
    # 2. Judul Utama (Sales Quotation) - Tengah Atas
    p.setFont('Helvetica-Bold', 22)
    p.setFillColor(colors.HexColor('#004d99')) # Darker Blue
    
    # REVISI BARIS RUSAK (Line 2081)
    # Pusatkan Judul secara vertikal di tengah area Logo (0.4 cm adalah offset visual/perkiraan)
    TITLE_Y = LOGO_Y_BOTTOM + (LOGO_HEIGHT / 2) - (0.4 * cm) 

    p.drawCentredString(width / 2, TITLE_Y, "SALES QUOTATION")
    
    # 3. Garis Pemisah (di bawah logo dan judul)
    LINE_SEPARATOR_Y = LOGO_Y_BOTTOM - 0.7 * cm
    p.setLineWidth(1)
    p.line(margin_x, LINE_SEPARATOR_Y, width - margin_x, LINE_SEPARATOR_Y)
    
    # Posisi Y Awal untuk Info Transaksi (di bawah Garis Pemisah)
    current_y = LINE_SEPARATOR_Y - 0.5 * cm
    
    # --- ZONA INFO: QUOTATION NO, DATE, VALID UNTIL ---
    
    p.setFillColor(colors.black)
    
    # Konstanta Posisi Info
    LINE_HEIGHT_INFO = 0.5 * cm
    COL_LABEL_X = margin_x
    COL_VALUE_X = margin_x + 3.8 * cm
    RIGHT_LABEL_X = width - margin_x - 3.8 * cm
    RIGHT_VALUE_X = width - margin_x

    # Baris 1: QUOTATION NO (Kiri) & DATE (Kanan)
    p.setFont('Helvetica-Bold', 10)
    p.drawString(COL_LABEL_X, current_y, "QUOTATION NO:")
    p.setFont('Helvetica', 10)
    p.drawString(COL_VALUE_X, current_y, f"{quotation.quotation_number or 'DRAFT'}")
    
    p.setFont('Helvetica-Bold', 10)
    p.drawString(RIGHT_LABEL_X, current_y, "DATE:")
    p.setFont('Helvetica', 10)
    p.drawRightString(RIGHT_VALUE_X, current_y, f"{quotation.date.strftime('%d %b %Y')}")
    current_y -= LINE_HEIGHT_INFO

    # Baris 2: VALID UNTIL (Kanan)
    p.setFont('Helvetica-Bold', 10)
    p.drawString(RIGHT_LABEL_X, current_y, "VALID UNTIL:")
    p.setFont('Helvetica', 10)
    valid_until_str = quotation.valid_until.strftime('%d %b %Y') if quotation.valid_until else 'N/A'
    p.drawRightString(RIGHT_VALUE_X, current_y, valid_until_str)
    current_y -= 1.0 * cm # Jarak sebelum ZONA 2
    
    # Garis pemisah sebelum ZONA 2
    p.line(margin_x, current_y, width - margin_x, current_y)
    current_y -= 0.8 * cm

    # --- ZONA 2: BILL TO (Kiri) & FROM (Kanan) ---
    
    current_y_col1 = current_y
    LEFT_COL_START = margin_x
    LEFT_COL_WIDTH = width / 2 - 1.0 * cm 
    
    # Judul Bill To / From
    p.setFont('Helvetica-Bold', 11)
    p.setFillColor(colors.HexColor('#333333'))
    p.drawString(LEFT_COL_START, current_y_col1, "BILL TO:")
    p.drawString(width / 2 + 0.5 * cm, current_y_col1, "FROM: (BRING.CO)")
    current_y_col1 -= 0.5 * cm

    # ... (lanjutan ZONA 2, 3, 4, 5)
    
    # --- KOLOM KIRI (BILL TO) ---
    p.setFont('Helvetica', 10)
    p.drawString(LEFT_COL_START, current_y_col1, f"Contact Person: {quotation.customer_name}")
    current_y_col1 -= 0.4 * cm
    p.drawString(LEFT_COL_START, current_y_col1, f"Phone: {quotation.customer_phone}")
    current_y_col1 -= 0.6 * cm 
    
    p.setFont('Helvetica-Bold', 10)
    p.drawString(LEFT_COL_START, current_y_col1, "Address:")
    current_y_col1 -= 0.4 * cm

    addr_text = quotation.customer_address
    addr_paragraph = Paragraph(addr_text, styleN) 
    
    addr_width = LEFT_COL_WIDTH
    addr_height = addr_paragraph.wrapOn(p, addr_width, height)[1]
    
    addr_paragraph.drawOn(p, LEFT_COL_START, current_y_col1 - addr_height)
    
    current_y_col1 -= addr_height + 0.1 * cm 
    
    
    # --- KOLOM KANAN (FROM) ---
    current_y_col2 = current_y # Gunakan current_y yang asli sebelum di-deduct oleh Bill To Judul
    right_x = width / 2 + 0.5 * cm
    RIGHT_COL_WIDTH = width / 2 - margin_x - 0.5 * cm
    
    # Adjust y_col2 start position to align with Bill To details
    current_y_col2 -= 0.5 * cm # Move down past 'FROM: (BRING.CO)' title
    
    p.setFont('Helvetica', 10)
    
    sender_text = (
        "Jl. Tebet Timur Dalam II No.7 Kec. Tebet, Jakarta Selatan 12820<br/>"
        "Email: bringco.hq@gmail.com<br/>"
        "Phone: +62-812-1414-4787"
    )
    sender_paragraph = Paragraph(sender_text, styleN)
    
    sender_height = sender_paragraph.wrapOn(p, RIGHT_COL_WIDTH, height)[1]

    sender_paragraph.drawOn(p, right_x, current_y_col2 - sender_height)
    
    current_y_col2 -= sender_height + 0.1 * cm

    current_y = min(current_y_col1, current_y_col2) - 0.5 * cm

    # --- ZONA 3: TABEL DETAIL ITEM ---
    
    p.setFont('Helvetica-Bold', 12)
    p.setFillColor(colors.HexColor('#004d99'))
    p.drawString(margin_x, current_y, "ITEMIZED QUOTATION DETAILS")
    current_y -= 0.5 * cm
    
    p.setLineWidth(0.5)
    p.line(margin_x, current_y, width - margin_x, current_y)
    current_y -= 0.1 * cm

    item_description_text = (
        f"<b>{quotation.sku.name}</b><br/>" 
        f"SKU ID: {quotation.sku.sku_id}<br/>"
        f"Kondisi/Status: {quotation.sku.get_status_display() or 'Ready Stock'}."
    )
    
    table_data = [
        ["No.", "Item Description (SKU ID)", "Quantity", "Unit Price (Rp)", "Line Total (Rp)"],
        [
            "1.",
            Paragraph(item_description_text, styleN), 
            f"{quotation.quantity}",
            f"{intcomma(quotation.price)}",
            f"{intcomma(quotation.get_subtotal)}"
        ]
    ]

    content_width = width - 2 * margin_x
    col_widths = [1 * cm, content_width * 0.48, 1.5 * cm, content_width * 0.20, content_width * 0.19,]
    
    item_table = Table(table_data, colWidths=col_widths)

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#004d99')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('ALIGN', (3, 1), (4, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), 
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ])
    item_table.setStyle(table_style)

    table_height = item_table.wrapOn(p, width, height)[1]
    current_y -= table_height

    item_table.drawOn(p, margin_x, current_y)
    
    # --- ZONA 4: RINGKASAN TOTALS (Kanan Bawah) & TERMS (Kiri Bawah) ---
    
    total_width = (width - 2 * margin_x) * 0.45 
    summary_x = width - margin_x - total_width
    SUMMARY_COL_WIDTHS_QUOTE = [total_width * 0.6, total_width * 0.4]
    
    current_y -= 0.5 * cm
    
    summary_data = [
        ["Subtotal:", f"Rp {intcomma(quotation.get_subtotal)}"],  
        ["Extra Discount:", f"Rp {intcomma(quotation.extra_discount)}"],
        ["TOTAL AMOUNT:", f"Rp {intcomma(quotation.get_total_quote)}"], 
    ]

    summary_table = Table(summary_data, colWidths=SUMMARY_COL_WIDTHS_QUOTE)

    summary_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -2), 10),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#B8860B')), 
        ('TOPPADDING', (0, -1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#004d99')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F0F8FF')),
    ])
    summary_table.setStyle(summary_style)

    summary_height = summary_table.wrapOn(p, width, height)[1]
    
    summary_table.drawOn(p, summary_x, current_y - summary_height)
    
    summary_bottom_y = current_y - summary_height
    
    # Terms and Conditions
    terms_x = margin_x
    TTD_RESERVED_Y = 5 * cm
    terms_y_start = min(current_y - 0.5 * cm, summary_bottom_y - 0.5 * cm) 
    
    if terms_y_start < TTD_RESERVED_Y:
        terms_y_start = TTD_RESERVED_Y
        
    p.setFont('Helvetica-Bold', 10)
    p.drawString(terms_x, terms_y_start, "TERMS AND CONDITIONS:")
    terms_y_start -= 0.5 * cm
    
    terms_list = [
        "- Payment Terms: Down Payment is due within 7 days of the invoice date.",
        "- Delivery Time: Estimated delivery time is 2-7 business days after order confirmation.",
        f"- Validity: This quotation is valid until {quotation.valid_until.strftime('%d %B %Y') if quotation.valid_until else 'N/A'}.",
        "- Warranty: All products come with a warranty. Details are available on request.",
        "- Shipping: Shipping cost is calculated based on the delivery location."
    ]
    
    p.setFont('Helvetica', 9)
    current_y_terms = terms_y_start
    line_spacing = 0.4 * cm
    for line in terms_list:
        p.drawString(terms_x, current_y_terms, line)
        current_y_terms -= line_spacing
        if current_y_terms < TTD_RESERVED_Y:
            break
            
    # --- ZONA 5: Approval (Pojok Kanan Bawah) ---
    
    ttd_x = width - margin_x - 5 * cm
    final_y_pos = 4 * cm 
    
    p.setFont('Helvetica-Bold', 10)
    p.drawCentredString(ttd_x + 2.5 * cm, final_y_pos, "Authorized Signature")
    
    p.line(ttd_x, final_y_pos - 1.0 * cm, ttd_x + 5 * cm, final_y_pos - 1.0 * cm)
    
    p.setFont('Helvetica-Bold', 10)
    p.drawCentredString(ttd_x + 2.5 * cm, final_y_pos - 1.5 * cm, "Approved by CEO") 
    p.setFont('Helvetica', 9)
    p.drawCentredString(ttd_x + 2.5 * cm, final_y_pos - 1.9 * cm, "CEO/Authorized Management")
    
    p.showPage()
    p.save()
    return response