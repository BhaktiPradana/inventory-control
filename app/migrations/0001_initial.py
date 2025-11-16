import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('po_number', models.CharField(max_length=100, unique=True)),
                ('expected_sku_count', models.IntegerField(default=0)),
                ('forwarder_receipt', models.FileField(blank=True, null=True, upload_to='receipts/')),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Delivered', 'Delivered'), ('Finished', 'Finished')], default='Pending', max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='SKU',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sku_id', models.CharField(help_text='SKU ID Mesin atau Aksesori', max_length=100, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('Receiving', 'Receiving'), ('QC', 'In QC'), ('Ready', 'Ready'), ('Delivering', 'Delivering to Shop'), ('Shop', 'Ready Shop')], default='Receiving', max_length=20)),
                ('location', models.CharField(choices=[('Warehouse', 'Warehouse'), ('Shop', 'Shop')], default='Warehouse', max_length=20)),
                ('shelf_location', models.CharField(blank=True, help_text='Diisi oleh Warehouse Manager', max_length=50, null=True)),
                ('assigned_technician', models.ForeignKey(blank=True, limit_choices_to={'groups__name': 'Technician'}, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('po_number', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skus', to='app.purchaseorder')),
            ],
        ),
        migrations.CreateModel(
            name='QCForm',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('condition_notes', models.TextField()),
                ('is_approved_by_lead', models.BooleanField(default=False)),
                ('lead_technician_comments', models.TextField(blank=True, null=True)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('technician', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='qc_forms', to=settings.AUTH_USER_MODEL)),
                ('sku', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='qc_form', to='app.sku')),
            ],
        ),
        migrations.CreateModel(
            name='MovementRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_by_shop', models.CharField(help_text='Nama toko atau peminta', max_length=100)),
                ('delivery_form', models.FileField(blank=True, null=True, upload_to='delivery_forms/')),
                ('status', models.CharField(choices=[('Pending', 'Pending Delivery'), ('Delivering', 'Delivering'), ('Received', 'Received at Shop')], default='Pending', max_length=20)),
                ('sku_to_move', models.ForeignKey(limit_choices_to={'status': 'Ready'}, on_delete=django.db.models.deletion.PROTECT, to='app.sku')),
            ],
        ),
        migrations.CreateModel(
            name='SparePartRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('part_name', models.CharField(max_length=255)),
                ('quantity_needed', models.IntegerField(default=1)),
                ('status', models.CharField(choices=[('Pending', 'Pending Warehouse Approval'), ('Approved_Buy', 'Approved (Need Purchase)'), ('Received', 'Received'), ('Issued', 'Issued to Technician')], default='Pending', max_length=20)),
                ('qc_form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='part_requests', to='app.qcform')),
                ('warehouse_manager', models.ForeignKey(blank=True, limit_choices_to={'groups__name': 'Warehouse Manager'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_requests', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='TechnicianAnalytics',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wrong_qc_count', models.IntegerField(default=0)),
                ('technician', models.OneToOneField(limit_choices_to={'groups__name': 'Technician'}, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
