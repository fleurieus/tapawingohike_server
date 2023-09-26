from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def format_duration(duration):
    if duration is None or duration == timedelta(hours=0, minutes=0):
        return ''
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}:{minutes}"