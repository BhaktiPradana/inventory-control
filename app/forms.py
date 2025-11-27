from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from .models import PurchaseOrder, SparePartInventory, StockAdjustment, SKU, SalesOrder, Payment, Quotation

class CustomUserCreationForm(UserCreationForm):
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(), 
        widget=forms.RadioSelect, 
        required=True, 
        label="Pilih Peran Anda" 
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('role',)

# Form untuk membuat PO oleh Purchasing
class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['po_number', 'expected_sku_count', 'buy_price']
        labels = {
            'po_number': 'Nomor PO',
            'expected_sku_count': 'Jumlah SKU Diharapkan',
            'buy_price': 'Harga Beli Total (Rp)'
            }
        widgets = {
            'po_number': forms.TextInput(attrs={'class': 'form-control'}),
            'expected_sku_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'buy_price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            }

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
