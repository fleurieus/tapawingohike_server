from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


# @register.filter
# def format_duration(duration):
#     if duration is None or duration == timedelta(hours=0, minutes=0):
#         return ''
#     hours, remainder = divmod(duration.seconds, 3600)
#     minutes, _ = divmod(remainder, 60)
#     return f"{hours}:{minutes}"
@register.filter
def format_duration(duration):
    if duration is None or duration == timedelta(hours=0, minutes=0):
        return ''
    
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Use f-strings for Python 3.6+
    return f"{hours:02}:{minutes:02}:{seconds:02}"