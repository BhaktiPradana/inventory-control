from django.db import models
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.db.models import Sum
from django.urls import reverse

# 1. Model untuk Proses Receiving
class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('Pending_Approval', 'Pending WH Approval'), # Baru
        ('Rejected', 'Rejected by WH'),          # Baru
        ('Pending', 'Pending Delivery'),         # Semula 'Pending'
        ('Delivered', 'Delivered'),              # PO Count != Total SKU
        ('Finished', 'Finished'),                # PO Count == Total SKU
    ]
    po_number = models.CharField(max_length=100, unique=True)
    expected_sku_count = models.IntegerField(default=0)
    total_po_price = models.DecimalField( 
        max_digits=10, 
        decimal_places=0, 
        default=0, 
        help_text="Harga Beli Total PO dari Supplier (Auto-Calculated)",
        null=True, 
        blank=True
    )
    forwarder_receipt = models.FileField(upload_to='receipts/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending_Approval') # Default diubah
    delivery_receipt = models.FileField(upload_to='po_delivery_receipts/', blank=True, null=True)
    # Field Baru untuk approval
    approved_by_wm = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_pos',
        limit_choices_to={'groups__name': 'Warehouse Manager'}
    )
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    managed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.po_number
class SKUDetailPO(models.Model):
    """Menyimpan detail mesin yang dipesan dalam satu PO."""
    purchase_order = models.ForeignKey(
        'PurchaseOrder',
        on_delete=models.CASCADE,
        related_name='sku_details',
        help_text="PO Induk dari detail mesin ini"
    )
    # Fields Wajib
    machine_sku_id = models.CharField(max_length=100, help_text="ID Mesin / SKU Item")
    machine_name = models.CharField(max_length=255, help_text="Nama Mesin / Tipe")
    color = models.CharField(max_length=50, help_text="Warna Mesin")
    po_price = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        help_text="Harga Beli PO per unit (Rp)"
    )
    
    # Field Opsional
    year = models.IntegerField(
        null=True,
        blank=True,
        help_text="Tahun pembuatan mesin (Opsional)"
    )

    def __str__(self):
        return f"{self.machine_name} - {self.machine_sku_id} (PO: {self.purchase_order.po_number})"



class Store(models.Model):
    """Model untuk merepresentasikan lokasi toko/outlet."""
    name = models.CharField(max_length=100, unique=True, help_text="Nama Store/Outlet")
    location_address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text="Apakah store ini aktif")
    
    def __str__(self):
        return self.name

class SalesAssignment(models.Model):
    """Menghubungkan user Sales dengan Store tertentu."""
    sales_person = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='store_assignment',
        limit_choices_to={'groups__name': 'Sales'},
        unique=True, # Satu Sales hanya punya satu Store aktif
        help_text="User Sales yang ditugaskan"
    )
    assigned_store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT, # Jangan hapus Store jika masih ada Sales
        related_name='assigned_sales',
        help_text="Store tempat Sales ditugaskan"
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'groups__name': 'Master Role'}, # Hanya Master Role yang bisa menugaskan
        help_text="Master Role yang menugaskan"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sales_person.username} ditugaskan di {self.assigned_store.name}"

class Rack(models.Model):
    # Kolom untuk representasi Rack (A-01, B-02, dll.)
    rack_location = models.CharField(max_length=50, unique=True, help_text="Lokasi fisik rak, cth: A1-01")

    # Status Available (Hijau) atau Used (Merah)
    STATUS_CHOICES = [
        ('Available', 'Available (Hijau)'),
        ('Used', 'Used (Merah)'),
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Available')

    # SKU yang menempati rak ini. Jika null, berarti Available.
    occupied_by_sku = models.OneToOneField(
        'SKU',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rack_slot',
        help_text="SKU yang saat ini menempati slot ini (null jika Available)"
    )
    
    # Kapan status terakhir diubah
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.rack_location

    class Meta:
        verbose_name = "Slot Rak Gudang"
        verbose_name_plural = "Slot Rak Gudang"
        ordering = ['rack_location']

class SKU(models.Model):
    STATUS_CHOICES = [
        ('Receiving', 'Receiving'),
        ('QC', 'In QC'),
        ('QC_PENDING', 'Pending Lead Approval'),
        ('AWAITING_INSTALL', 'Awaiting Part Installation'), 
        ('PENDING_FINAL_CHECK', 'Pending Final Check'),    
        ('Ready', 'Ready'),
        ('Delivering', 'Delivering to Shop'),
        ('Shop', 'Ready Shop'),
        ('Booked', 'Booked'), 
        ('Sold', 'Sold'),
    ]
    current_store = models.ForeignKey(
        Store,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skus_in_store',
        limit_choices_to={'is_active': True}, # Hanya bisa Store yang aktif
        help_text="Store tempat SKU ini berada saat status='Shop'"
    )
    LOCATION_CHOICES = [
        ('Warehouse', 'Warehouse'),
        ('Shop', 'Shop'),
    ]
    sku_id = models.CharField(max_length=100, unique=True, help_text="SKU ID Mesin atau Aksesori")
    name = models.CharField(max_length=255)
    po_number = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='skus')
    assigned_technician = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        limit_choices_to={'groups__name': 'Technician'}
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Receiving')
    location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='Warehouse')
    shelf_location = models.ForeignKey(
        Rack, # Menggunakan model Rack yang baru
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stored_skus',
        help_text="Slot rak tempat SKU ini diletakkan."
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    shelved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.sku_id} - {self.name}"
    def get_absolute_url(self):
        return reverse('sku_history', args=[str(self.id)])

# 2. Model untuk Proses Inventory (QC)
class QCForm(models.Model):
    sku = models.OneToOneField(SKU, on_delete=models.CASCADE, related_name='qc_form')
    technician = models.ForeignKey(User, on_delete=models.PROTECT, related_name='qc_forms')
    qc_document_file = models.FileField(
        upload_to='qc_documents/', 
        blank=True, 
        null=True, 
        help_text="File QC form (PDF, docx, etc.)"
    )
    condition_notes = models.TextField()
    is_approved_by_lead = models.BooleanField(default=False)
    lead_technician_comments = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    managed_at = models.DateTimeField(null=True, blank=True)
    photo_before_install = models.ImageField(upload_to='qc_photos/before/', blank=True, null=True)
    photo_after_install = models.ImageField(upload_to='qc_photos/after/', blank=True, null=True)
    installation_notes = models.TextField(blank=True, null=True)
    installation_submitted_at = models.DateTimeField(null=True, blank=True)
    final_approval_at = models.DateTimeField(null=True, blank=True) # Kapan lead tech approve final
    final_lead_comments = models.TextField(blank=True, null=True) # Komentar lead tech (jika re-check gagal)
    final_managed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp final check (approve/reject)")

    def __str__(self):
        return f"QC Form for {self.sku.sku_id}"
class InstallationPhoto(models.Model):
    PHOTO_TYPE_CHOICES = [
        ('before', 'Before Installation'),
        ('after', 'After Installation'),
    ]
    qc_form = models.ForeignKey(QCForm, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='installation_photos/')
    photo_type = models.CharField(max_length=10, choices=PHOTO_TYPE_CHOICES)
    remarks = models.CharField(max_length=255, blank=True, null=True, help_text="Keterangan foto")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.photo_type} - {self.qc_form.sku.sku_id}"

class SparePartRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending Warehouse Approval'),
        ('Approved_Buy', 'Approved (Need Purchase)'),
        ('Received', 'Received'),
        ('PENDING_LEAD_RECEIPT', 'Pending Lead Receipt Approval'),
        ('Issued', 'Issued to Technician'),
        ('Rejected', 'Rejected by Lead'), 
    ]
    qc_form = models.ForeignKey(QCForm, on_delete=models.CASCADE, related_name='part_requests')
    part_name = models.CharField(max_length=255)
    quantity_needed = models.IntegerField(default=1)
    issued_spare_part = models.ForeignKey(
        'SparePartInventory', # Menggunakan string karena didefinisikan setelahnya
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_requests',
        help_text="Part dari inventory yang dikeluarkan oleh WM."
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    warehouse_manager = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_requests',
        limit_choices_to={'groups__name': 'Warehouse Manager'}
    )
    lead_receipt_approver = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_part_receipts',
        limit_choices_to={'groups__name': 'Lead Technician'}
    )
    lead_receipt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    managed_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        issued_sku = self.issued_spare_part.part_sku if self.issued_spare_part else 'N/A'
        return f"{self.quantity_needed}x {self.part_name} (SKU: {issued_sku}) for {self.qc_form.sku.sku_id}"

class TechnicianAnalytics(models.Model):
    technician = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        limit_choices_to={'groups__name': 'Technician'}
    )
    wrong_qc_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Analytics for {self.technician.username}"

# 3. Model untuk Proses Movement
class MovementRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending Delivery'),
        ('Delivering', 'Delivering'),
        ('Received', 'Received at Shop'),
    ]
    sku_to_move = models.ForeignKey(
        SKU, 
        on_delete=models.PROTECT, 
        related_name='movements', # Tambah related_name
        limit_choices_to={'status': 'Ready'}
    )
    # REVISI 1 & 3: Mengganti CharField menjadi ForeignKey ke Store
    requested_by_store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        null=True, 
        blank=True,
        related_name='incoming_movements',
        help_text="Store Tujuan Pengiriman"
    )
    # requested_by_shop = models.CharField(max_length=100, help_text="Nama toko atau peminta") # Dihapus
    delivery_form = models.FileField(upload_to='delivery_forms/', blank=True, null=True)
    receipt_form = models.FileField(upload_to='movement_receipts/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Delivering') # Default diubah ke Delivering
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    
    # REVISI 3: Menambahkan field Sales yang menerima
    received_by_sales = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_movements',
        limit_choices_to={'groups__name': 'Sales'}
    )

    def __str__(self):
        # Menggunakan Store Name
        return f"Movement request for {self.sku_to_move.sku_id} to {self.requested_by_store.name}"

class PurchasingNotification(models.Model):
    po_number = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField(help_text="Alasan mengapa packing list tidak sesuai")
    reported_by = models.ForeignKey(User, on_delete=models.PROTECT, limit_choices_to={'groups__name': 'Warehouse Manager'})
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"Notifikasi untuk PO: {self.po_number.po_number}"

class SparePartInventory(models.Model):
    STATUS_CHOICES = [
        ('Ready', 'Ready'),
        ('On_Order', 'On Order (Dipesan)'),
        ('In_QC', 'In QC'),
        ('Out_Of_Stock', 'Out of Stock'),
        ('Pending_Adjustment', 'Pending Adjustment'),
    ]
    ORIGIN_CHOICES = [
        ('MANUAL', 'Manual Entry'),      # Part yang diregister manual oleh WM
        ('PURCHASE', 'New Purchase'),    # Part baru hasil pembelian
        ('RETURN', 'Old Part Return'),   # Part lama kembalian dari Lead Tech
    ]
    
    part_name = models.CharField(max_length=255, unique=True, help_text="Nama unik spare part, cth: 'Sensor Tipe X'")
    part_sku = models.CharField(max_length=100, unique=True, blank=True, null=True, help_text="SKU internal untuk spare part ini")
    quantity_in_stock = models.PositiveIntegerField(default=0, help_text="Jumlah stok yang ada di gudang")
    location = models.CharField(max_length=100, blank=True, null=True, help_text="Lokasi rak di gudang, cth: B-01-TOP")
    primary_supplier = models.CharField(max_length=255, blank=True, null=True, help_text="Nama supplier utama part ini")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Out_Of_Stock')
    origin = models.CharField(max_length=10, choices=ORIGIN_CHOICES, default='MANUAL')

    def __str__(self):
        return f"{self.part_name} (Stok: {self.quantity_in_stock})"
    def has_pending_adjustment(self):
        return self.adjustments.filter(status='Pending').exists()

class StockAdjustment(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    
    # Part mana yang disesuaikan
    spare_part = models.ForeignKey(
        SparePartInventory, 
        on_delete=models.CASCADE, 
        related_name='adjustments'
    )
    # Siapa yang me-request (WM)
    requested_by = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name='stock_adjustments_requested',
        limit_choices_to={'groups__name': 'Warehouse Manager'}
    )
    # Siapa yang me-manage (Purchasing)
    managed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='stock_adjustments_managed',
        limit_choices_to={'groups__name': 'Purchasing'}
    )
    
    # Data Kuantitas
    quantity_in_system = models.PositiveIntegerField()
    quantity_actual = models.PositiveIntegerField(help_text="Jumlah fisik hasil perhitungan")
    
    # Data Pendukung
    reason = models.TextField(help_text="Alasan penyesuaian (cth: Stock opname, barang rusak, hilang)")
    rejection_reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    managed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Adjustment for {self.spare_part.part_name} (from {self.quantity_in_system} to {self.quantity_actual})"

    @property
    def difference(self):
        return self.quantity_actual - self.quantity_in_system
class ReturnedPart(models.Model):
    STATUS_CHOICES = [
        ('Pending_Lead', 'Pending Lead Approval'),
        ('Approved', 'Approved (In Stock)'),
        ('Rejected', 'Rejected by Lead'),
    ]
    # Terhubung ke form QC mana
    qc_form = models.ForeignKey(QCForm, on_delete=models.CASCADE, related_name='returned_parts')
    
    # Data dari Teknisi
    part_name_reported = models.CharField(max_length=255, help_text="Nama part lama yang dilaporkan Teknisi")
    reported_at = models.DateTimeField(auto_now_add=True)
    
    # Data dari Lead Technician (WAJIB DIISI SAAT APPROVE)
    lead_assigned_sku = models.CharField(max_length=100, blank=True, null=True, help_text="SKU part lama yang diisi oleh Lead")
    
    # Status Approval
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending_Lead')
    approved_by_lead = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_returned_parts',
        limit_choices_to={'groups__name': 'Lead Technician'}
    )
    managed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Return: {self.part_name_reported} for {self.qc_form.sku.sku_id}"

class Quotation(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent to Customer'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Converted', 'Converted to Order'),
    ]
    quotation_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    extra_discount = models.DecimalField(max_digits=10, decimal_places=0, default=0, help_text="Diskon tambahan (Rp)")
    
    # 1. Data Customer
    customer_name = models.CharField(max_length=255)
    customer_address = models.TextField()
    customer_phone = models.CharField(max_length=20)
    
    sku = models.ForeignKey(
        SKU, 
        on_delete=models.PROTECT, 
        related_name='quotations',
    )
    quantity = models.PositiveIntegerField(default=1, help_text="Jumlah unit yang di-quote")
    price = models.DecimalField(max_digits=10, decimal_places=0, help_text="Harga yang ditawarkan")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    sales_person = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name='quotations',
        limit_choices_to={'groups__name': 'Sales'}
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    converted_to_order = models.ForeignKey(
        'SalesOrder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='converted_quotations',
        help_text="Order hasil konversi dari quotation ini"
    )

    def __str__(self):
        return f"Quotation {self.quotation_number or self.id} - {self.customer_name} ({self.sku.sku_id})"
    
    @property
    def get_subtotal(self):
        """Menghitung subtotal sebelum diskon."""
        return self.price * self.quantity

    @property
    def get_total_quote(self):
        """Menghitung total harga quotation (Subtotal - Diskon)."""
        return self.get_subtotal - self.extra_discount

class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending Payment'), # Baru dibuat
        ('Booked', 'Booked'),           # Sudah ada DP
        ('Sold', 'Sold'),               # Lunas
        ('Shipped', 'Shipped'),         # Sudah dikirim
        ('Completed', 'Completed'),     # Sudah diterima customer
    ]

    # 1. Data Customer
    customer_name = models.CharField(max_length=255)
    customer_address = models.TextField()
    customer_phone = models.CharField(max_length=20)
    
    # 2. Data SKU
    sku = models.ForeignKey(
        SKU, 
        on_delete=models.PROTECT, 
        related_name='sales_orders',
        limit_choices_to={'status': 'Shop'} # Hanya bisa pilih SKU 'Ready Store'
    )
    price = models.DecimalField(max_digits=10, decimal_places=0, help_text="Harga final penjualan")
    
    # 3. Data Pembayaran (dikelola oleh model Payment)
    
    # 4. Data Pengiriman
    shipping_type = models.CharField(max_length=100, blank=True, null=True, help_text="Contoh: JNE, J&T, Diambil Sendiri")
    shipping_receipt = models.FileField(upload_to='sales/shipping_receipts/', blank=True, null=True, help_text="Resi Pengiriman")
    proof_of_receipt = models.FileField(upload_to='sales/proof_of_receipts/', blank=True, null=True, help_text="Bukti Penerimaan oleh Customer")
    shipped_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp saat resi pengiriman diupload")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp saat bukti penerimaan diupload")
    
    # 5. Status & Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    sales_person = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name='sales_orders',
        limit_choices_to={'groups__name': 'Sales'}
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} - {self.customer_name} ({self.sku.sku_id})"

    def get_total_paid(self):
        """Menghitung total pembayaran yang sudah masuk."""
        total = self.payments.aggregate(total=Sum('amount'))['total']
        return total or 0

    def get_remaining_balance(self):
        """Menghitung sisa tagihan."""
        return self.price - self.get_total_paid()

    def update_status_based_on_payment(self):
        """Logika untuk update status order DAN SKU."""
        total_paid = self.get_total_paid()
        
        if total_paid >= self.price:
            self.status = 'Sold'
            self.sku.status = 'Sold'
        elif total_paid > 0:
            self.status = 'Booked'
            self.sku.status = 'Booked'
        else:
            # Jika tidak ada pembayaran (misal dibatalkan/dihapus), kembalikan status
            self.status = 'Pending'
            self.sku.status = 'Shop' # Kembali jadi Ready Store
            
        self.save()
        self.sku.save()

class Payment(models.Model):
    """Mencatat setiap pembayaran yang masuk untuk SalesOrder."""
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=0)
    proof_of_transfer = models.FileField(upload_to='sales/payment_proofs/')
    payment_date = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"Payment {self.id} for Order {self.sales_order.id} - {self.amount}"



