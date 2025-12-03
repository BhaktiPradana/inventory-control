# app/migrations/0025_clean_sku_shelf_location.py

from django.db import migrations

def set_existing_shelf_location_to_null(apps, schema_editor):
    """
    Mengubah semua nilai yang ada di SKU.shelf_location yang bukan NULL
    menjadi NULL, agar kolom aman diubah tipenya (ke Foreign Key) nanti.
    """
    # Mengambil model SKU dari migrasi sebelumnya (sebelum Foreign Key)
    SKU = apps.get_model('app', 'SKU')
    
    # Membersihkan semua baris yang memiliki nilai non-NULL
    # Ini akan mengubah data CharField lama menjadi NULL
    SKU.objects.exclude(shelf_location__isnull=True).update(shelf_location=None)


class Migration(migrations.Migration):

    dependencies = [
        # Dependensi harus menunjuk ke migrasi terakhir yang SUKSES DITERAPKAN (0023)
        ('app', '0023_remove_movementrequest_requested_by_shop_and_more'), 
    ]

    operations = [
        # Jalankan operasi pembersihan data
        migrations.RunPython(set_existing_shelf_location_to_null, migrations.RunPython.noop),
    ]