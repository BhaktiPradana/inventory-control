from django.urls import path
from . import views 
from .views import SignUpView
from django.contrib.auth import views as auth_views

urlpatterns = [
    # 1. Halaman Dashboard (saat user sudah login)
    path('', views.dashboard, name='dashboard'),

    # 2. Halaman Login
    path('login/', auth_views.LoginView.as_view(template_name='app/login.html'), name='login'),

    # 3. Proses Logout
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # URLs Receiving (WM)
    path('receiving/', views.receiving_list, name='receiving_list'),
    path('receiving/<int:po_id>/', views.receiving_detail, name='receiving_detail'),
    
    # URLs PO Approval (Purchasing & WM) 
    path('po/create/', views.po_create, name='po_create'),
    path('po/approve/', views.po_approve_list, name='po_approve_list'),
    path('po/approve/<int:po_id>/', views.po_approve_detail, name='po_approve_detail'),
    
    # URLs QC (Technician & Lead)
    path('qc/form/<int:sku_id>/', views.qc_form, name='qc_form'),
    path('qc/verify/<int:qc_id>/', views.qc_verify, name='qc_verify'),
    path('qc/install/<int:qc_id>/', views.installation_form, name='installation_form'),
    path('qc/final-check/<int:qc_id>/', views.final_check, name='final_check'),

    path('sparepart/approve-receipt/<int:part_id>/', views.approve_part_receipt, name='approve_part_receipt'),
    # URLs Sparepart (WM & Purchasing)
    path('sparepart/manage/<int:request_id>/', views.manage_sparepart, name='manage_sparepart'),
    path('sparepart/received/<int:request_id>/', views.mark_part_received, name='mark_part_received'),
    
    # URLs Inventory (WM)
    path('movement/', views.movement_process, name='movement_process'),

    path('inventory/', views.inventory_dashboard, name='inventory_dashboard'),
    path('inventory/add/', views.inventory_add, name='inventory_add'),
    path('inventory/edit/<int:part_id>/', views.inventory_edit, name='inventory_edit'),
    path('inventory/adjust/<int:part_id>/', views.inventory_adjust, name='inventory_adjust'),
    path('inventory/approve-adjustment/<int:adj_id>/', views.approve_stock_adjustment, name='approve_stock_adjustment'),
    #HALAMAN HISTORY
    path('sku/history/<int:sku_id>/', views.sku_history, name='sku_history'),
    path('sku/history/modal/<int:sku_id>/', views.get_sku_history_modal, name='sku_history_modal'),
    # URL Registrasi
    path('register/', SignUpView.as_view(), name='register'),
    path('inventory/history/<str:part_name>/', views.get_part_usage_history, name='part_usage_history'),
    path('inventory/api/search/', views.inventory_search_api, name='inventory_search_api'),

    path('master-role/', views.master_role_dashboard, name='master_role_dashboard'),
    
    # Kelola Store
    path('master-role/store/', views.store_list, name='store_list'),
    path('master-role/store/add/', views.store_add, name='store_add'),
    path('master-role/store/edit/<int:store_id>/', views.store_edit, name='store_edit'),
    path('master-role/store/delete/<int:store_id>/', views.store_delete, name='store_delete'),

    # Kelola Penugasan Sales
    path('master-role/sales-assignment/', views.sales_assignment_list, name='sales_assignment_list'),
    path('master-role/sales-assignment/add/', views.sales_assignment_add, name='sales_assignment_add'),
    path('master-role/sales-assignment/edit/<int:assignment_id>/', views.sales_assignment_edit, name='sales_assignment_edit'),

    path('sales/order/add/', views.sales_order_add, name='sales_order_add'),
    path('sales/order/<int:order_id>/', views.sales_order_detail, name='sales_order_detail'),
    path('sales/order/<int:order_id>/payment/', views.add_payment, name='add_payment'),
    path('sales/order/<int:order_id>/shipping/', views.upload_shipping_files, name='upload_shipping_files'),
    path('sales/order/<int:order_id>/process_shipping/', views.process_shipping, name='process_shipping'),
    path('sales/quotation/add/', views.quotation_add, name='quotation_add'),
    path('sales/quotation/<int:quotation_id>/convert/', views.convert_quotation_to_order, name='convert_to_order'),
    path('sales/quotation/<int:quotation_id>/', views.quotation_detail, name='quotation_detail'),
    path('sales/order/<int:order_id>/print_label/', views.print_order_label, name='print_order_label'),
    path('sales/order/<int:order_id>/print_invoice/', views.print_invoice_a4, name='print_invoice_a4'),
    path('sales/quotation/<int:quotation_id>/print_a4/', views.print_quotation_a4, name='print_quotation_a4'),
    path('sales/order/<int:order_id>/print_label/', views.print_order_label, name='print_order_label'),
    path('sales/receive-sku/<int:movement_id>/', views.sales_receive_sku, name='sales_receive_sku'),

    path('rack/list/', views.rack_list, name='rack_list'),
    path('rack/add/', views.rack_add, name='rack_add'),
    path('rack/edit/<int:rack_id>/', views.rack_edit, name='rack_edit'),
    path('rack/delete/<int:rack_id>/', views.rack_delete, name='rack_delete'),
    path('rack/view/', views.rack_grid_view, name='rack_grid_view'),
]