from django.contrib import admin
from .models import PurchasingNotification
from .models import (
    PurchaseOrder, 
    SKU, 
    QCForm, 
    SparePartRequest, 
    TechnicianAnalytics, 
    MovementRequest,
    SparePartInventory,
    StockAdjustment,
    SalesOrder, 
    Payment,
    Quotation
)

admin.site.register(PurchaseOrder)
admin.site.register(SKU)
admin.site.register(QCForm)
admin.site.register(SparePartRequest)
admin.site.register(TechnicianAnalytics)
admin.site.register(MovementRequest)
admin.site.register(PurchasingNotification)
admin.site.register(SparePartInventory)
admin.site.register(StockAdjustment)
admin.site.register(SalesOrder)
admin.site.register(Payment)
admin.site.register(Quotation)