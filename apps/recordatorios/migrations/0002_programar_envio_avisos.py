from django.db import migrations

NOMBRE = "enviar_recordatorios_vencidos"


def programar(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.update_or_create(
        name=NOMBRE,
        defaults={
            "func": "apps.recordatorios.tareas.enviar_vencidos",
            "schedule_type": "I",  # cada N minutos
            "minutes": 1,
            "repeats": -1,
        },
    )


def desprogramar(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(name=NOMBRE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("recordatorios", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(programar, desprogramar)]
