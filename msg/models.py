from django.db import models

class Msg(models.Model):
    sender = models.ForeignKey('member.Member', null=True, blank=True, on_delete=models.SET_NULL)
    guest_name = models.CharField(max_length=50, blank=True, null=True)
    recipient = models.ForeignKey('member.Member', related_name='received_messages', null=True, blank=True, on_delete=models.SET_NULL)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    