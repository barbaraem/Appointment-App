from __future__ import unicode_literals

import arrow

from appointment_reminders import celery_app
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from timezone_field.fields import TimeZoneField




class Appointment(models.Model):
    name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=9)
    time = models.DateTimeField()
    time_zone = TimeZoneField(default="Europe/Warsaw")

    # additional fields:
    task_id = models.CharField(max_length=150, blank=True, editable=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__ (self):
        return "Appointment number:{} - {} ".format(self.pk, self.name)

    def get_absolute_url(self):
        return reverse('view_appointment', args=[str(self.id)])


    def clean(self):
        """Checks that appointments are not scheduled in the past"""

        appointment_time = arrow.get(self.time, self.time_zone.zone)

        if appointment_time < arrow.now('Europe/Warsaw'):
            raise ValidationError('You cannot schedule an appointment for the past. '
                                  'Please check your time and time_zone')


    def schedule_reminder(self):
        """Schedules a Celery task to send a reminder about this appointment"""

        #calculate time to send the reminder
        appointment_time = arrow.get (self.time, self.time_zone.zone)
        reminder_time = appointment_time.replace(minutes=-settings.REMINDER_TIME)

        # schedule the celery task
        from .tasks import send_sms_reminder
        result = send_sms_reminder.apply_async((self.pk,), eta=reminder_time)

        return result.id

    def save(self, *args, **kwargs):
        """Custom save method which also schedules a reminder"""

        # Check if we have scheduled a reminder for this appointment before
        if self.task_id:
            # Revoke that task in case its time has changed
            celery_app.control.revoke(self.task_id)

        # Save appointment, which populates self.pk,which is used in schedule_reminder
        super(Appointment, self).save(*args, **kwargs)

        # Schedule a new reminder task for this appointment
        self.task_id = self.schedule_reminder()

        # Save our appointment again, with the new task_id
        super(Appointment, self).save(*args, **kwargs)

