from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from .models import PurchaseOrder, SparePartInventory, StockAdjustment, SKU, SalesOrder, Payment, Quotation, Store, SalesAssignment, MovementRequest, Rack

class CustomUserCreationForm(UserCreationForm):
    role = forms.ModelChoiceField(
        queryset=None, 
        widget=forms.RadioSelect,
        required=True,
        label="Pilih Peran Anda"
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('role',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            # Dapatkan ID Master Role
            master_role_id = Group.objects.get(name='Master Role').id
            self.fields['role'].queryset = Group.objects.exclude(id=master_role_id)
            
        except Group.DoesNotExist:
            self.fields['role'].queryset = Group.objects.all()
        
        except Exception:
            self.fields['role'].queryset = Group.objects.all()

# Form untuk membuat PO oleh Purchasing
class PurchaseOrderForm(forms.ModelForm):

    class Meta:
        model = PurchaseOrder
        # Pastikan field utama dan suggested_rack disertakan:
        fields = ['po_number', 'expected_sku_count', 'buy_price', 'suggested_rack'] 
        labels = {
            'po_number': 'Nomor PO',
            'expected_sku_count': 'Jumlah SKU Diharapkan',
            'buy_price': 'Harga Beli Total (Rp)',
            'suggested_rack': 'Saran Lokasi Rak'
        }
        widgets = {
            'po_number': forms.TextInput(attrs={'class': 'form-control'}),
            'expected_sku_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'buy_price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}), 
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 1. Mengatur Queryset untuk suggested_rack (ForeignKey)
        if 'suggested_rack' in self.fields:
            self.fields['suggested_rack'].queryset = Rack.objects.filter(
                status='Available', 
                occupied_by_sku__isnull=True
            ).order_by('rack_location')
            
            # 2. Menyembunyikan widget field model agar diurus oleh input hidden di HTML
            self.fields['suggested_rack'].widget = forms.HiddenInput()
            self.fields['suggested_rack'].label = ''
            

# Form untuk WM me-reject PO
class PORejectionForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['rejection_reason']
        labels = {
            'rejection_reason': 'Alasan Penolakan (Wajib diisi)'
        }
        widgets = {
            'rejection_reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'required': True})
        }

class SparePartInventoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nonaktifkan field stok
        self.fields['quantity_in_stock'].disabled = True
        self.fields['quantity_in_stock'].help_text = "Jumlah stok tidak bisa diubah dari sini. Gunakan fitur 'Adjust Stock' di dashboard inventory."
    class Meta:
        model = SparePartInventory
        fields = ['part_name', 'part_sku', 'quantity_in_stock', 'location', 'primary_supplier', 'status']
        labels = {
            'part_name': 'Nama Spare Part',
            'part_sku': 'SKU Spare Part (Opsional)',
            'quantity_in_stock': 'Jumlah Stok di Sistem', 
            'location': 'Lokasi di Gudang',
            'primary_supplier': 'Supplier Utama (Opsional)',
            'status': 'Status Stok'
        }
        widgets = {
            'part_name': forms.TextInput(attrs={'class': 'form-control'}),
            'part_sku': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity_in_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'primary_supplier': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['quantity_actual', 'reason']
        labels = {
            'quantity_actual': 'Jumlah Aktual (Hasil Hitungan Fisik)',
            'reason': 'Alasan Penyesuaian (Wajib diisi)',
        }
        widgets = {
            'quantity_actual': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class StockAdjustmentRejectForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['rejection_reason']
        labels = {
            'rejection_reason': 'Alasan Penolakan (Wajib diisi)',
        }
        widgets = {
            'rejection_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'required': True}),
        }

class SalesOrderForm(forms.ModelForm):
    """Form untuk tombol '+ Add Customer'."""
    
    # Filter SKU agar hanya menampilkan yang 'Ready Store'
    sku = forms.ModelChoiceField(
        queryset=SKU.objects.filter(status='Shop'),
        label='SKU Mesin (Hanya status Ready Store)',
        widget=forms.Select(attrs={'class': 'form-select select2-sku', 'data-placeholder': 'Cari SKU Ready Store...'})
    )

    class Meta:
        model = SalesOrder
        fields = [
            'customer_name', 'customer_address', 'customer_phone', 
            'sku', 'price', 'shipping_type'
        ]
        labels = {
            'customer_name': 'Nama Customer',
            'customer_address': 'Alamat Customer',
            'customer_phone': 'Nomor Telepon',
            'sku': 'SKU ID Mesin',
            'price': 'Harga Jual (Final)',
            'shipping_type': 'Jenis Pengiriman'
        }
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'customer_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'customer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'shipping_type': forms.TextInput(attrs={'class': 'form-control'}),
        }

class QuotationForm(forms.ModelForm):
    """Form untuk membuat Quotation."""
    
    quotation_number = forms.CharField(
        max_length=100, 
        required=False, 
        label='Nomor Quotation (Opsional)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Q-2025/01/001'})
    )
    
    valid_until = forms.DateField(
        label='Berlaku Sampai Tanggal',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True # Wajib diisi untuk Quotation
    )

    # Tidak perlu filter 'Ready Store' untuk Quotation
    sku = forms.ModelChoiceField(
        queryset=SKU.objects.filter(status='Shop'), 
        label='SKU Mesin ID (Hanya Ready Store)',
        widget=forms.Select(attrs={'class': 'form-select select2-sku', 'data-placeholder': 'Cari SKU Ready Store...'})
    )

    class Meta:
        model = Quotation
        fields = [
            'quotation_number', 'valid_until',
            'sku', 'customer_name', 'customer_address', 'customer_phone', 
            'quantity', 'price', 'extra_discount' 
        ]
        labels = {
            'sku': 'SKU ID Mesin',
            'customer_name': 'Nama Customer',
            'customer_address': 'Alamat Customer',
            'customer_phone': 'Nomor Telepon',
            'quantity': 'Jumlah Unit Order',
            'price': 'Harga Jual per Unit',
            'extra_discount': 'Extra Discount (Rp)'
        }
        widgets = {
            'sku': forms.Select(attrs={'class': 'form-select select2-sku'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'customer_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'customer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'extra_discount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}), 
        }

class PaymentForm(forms.ModelForm):
    """Form untuk menambah pembayaran (pertama atau selanjutnya)."""
    class Meta:
        model = Payment
        fields = ['amount', 'proof_of_transfer']
        labels = {
            'amount': 'Jumlah Pembayaran',
            'proof_of_transfer': 'Upload Bukti Transfer'
        }
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'proof_of_transfer': forms.FileInput(attrs={'class': 'form-control', 'required': True}),
        }

class ShippingFileForm(forms.ModelForm):
    """Form untuk upload Resi Pengiriman dan Bukti Penerimaan."""
    class Meta:
        model = SalesOrder
        fields = ['shipping_receipt', 'proof_of_receipt']
        labels = {
            'shipping_receipt': 'Upload File Resi Pengiriman',
            'proof_of_receipt': 'Upload Bukti Penerimaan Customer'
        }
        widgets = {
            'shipping_receipt': forms.FileInput(attrs={'class': 'form-control'}),
            'proof_of_receipt': forms.FileInput(attrs={'class': 'form-control'}),
        }

class StoreForm(forms.ModelForm):
    """Form untuk menambah/mengedit Store."""
    class Meta:
        model = Store
        fields = ['name', 'location_address', 'is_active']
        labels = {
            'name': 'Nama Store',
            'location_address': 'Alamat Lokasi Store',
            'is_active': 'Status Aktif'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# --- FORM BARU UNTUK PENUGASAN SALES KE STORE ---
class SalesAssignmentForm(forms.ModelForm):
    """Form untuk Master Role menugaskan Sales ke Store."""
    sales_person = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name='Sales'),
        label='Pilih Sales Person',
        widget=forms.Select(attrs={'class': 'form-select select2-user'})
    )
    assigned_store = forms.ModelChoiceField(
        queryset=Store.objects.filter(is_active=True),
        label='Store yang Ditugaskan',
        widget=forms.Select(attrs={'class': 'form-select select2-store'})
    )
    
    class Meta:
        model = SalesAssignment
        fields = ['sales_person', 'assigned_store']

class MovementRequestForm(forms.ModelForm):
    """Form untuk Warehouse Manager membuat Movement Request baru."""
    # Memilih Store tujuan
    requested_by_store = forms.ModelChoiceField(
        queryset=Store.objects.filter(is_active=True),
        label='Diminta oleh (Store/Shop)',
        widget=forms.Select(attrs={'class': 'form-select select2-store', 'required': True})
    )
    
    # Memilih SKU yang siap pindah
    sku_to_move = forms.ModelChoiceField(
        queryset=SKU.objects.filter(status='Ready', shelf_location__isnull=False),
        label='Pilih SKU (Barang Ready Gudang)',
        widget=forms.Select(attrs={'class': 'form-select select2-sku-move', 'required': True, 'data-placeholder': 'Cari SKU Ready...'})
    )

    class Meta:
        model = MovementRequest
        fields = ['sku_to_move', 'requested_by_store', 'delivery_form']
        labels = {
            'delivery_form': 'Upload Form Pengiriman (DO)',
        }
        widgets = {
            'delivery_form': forms.FileInput(attrs={'class': 'form-control form-control-lg shadow-sm', 'required': True}),
        }

class RackSelectionForm(forms.Form):
    # Hanya menampilkan rak yang 'Available' (Hijau) DAN belum ditempati
    available_racks = forms.ModelChoiceField(
        queryset=Rack.objects.filter(status='Available', occupied_by_sku__isnull=True),
        label="Pilih Lokasi Rak (Hijau = Available)",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select select2-rack-available'})
    )


class RackForm(forms.ModelForm):
    """Form untuk menambah/mengedit Rak Gudang."""
    class Meta:
        model = Rack
        fields = ['rack_location', 'status']
        labels = {
            'rack_location': 'Lokasi Rak (Contoh: A1-01)',
            'status': 'Status Awal'
        }
        widgets = {
            'rack_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: A1-01'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
    
    # Menonaktifkan status untuk mencegah user mengubahnya di form create/edit biasa
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Status akan diatur secara otomatis saat membuat, atau diubah oleh sistem (saat ditempati)
        if self.instance and self.instance.occupied_by_sku:
             self.fields['status'].disabled = True
             self.fields['status'].help_text = "Status tidak bisa diubah karena rak sedang terisi."