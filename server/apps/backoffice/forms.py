from django import forms
from server.apps.dashboard.models import Destination
from server.apps.dashboard.models import Route, RoutePart, File, Destination
from server.apps.dashboard.constants import FILE_TYPE_IMAGE, FILE_TYPE_AUDIO

class DestinationForm(forms.ModelForm):
    class Meta:
        model = Destination
        fields = ["lat", "lng", "destination_type", "radius", "confirm_by_user", "hide_for_user"]
        widgets = {
            "lat":  forms.NumberInput(attrs={"step":"any", "class":"border rounded px-2 py-1 w-full"}),
            "lng":  forms.NumberInput(attrs={"step":"any", "class":"border rounded px-2 py-1 w-full"}),
            "destination_type": forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "radius": forms.NumberInput(attrs={"class":"border rounded px-2 py-1 w-full", "min":"1"}),
            "confirm_by_user": forms.CheckboxInput(attrs={"class":"h-4 w-4"}),
            "hide_for_user":   forms.CheckboxInput(attrs={"class":"h-4 w-4"}),
        }

class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = ["name", "edition"]
        widgets = {
            "name": forms.TextInput(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "edition": forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
        }

class RoutePartForm(forms.ModelForm):
    # gefilterde file-keuzes op category
    routedata_image = forms.ModelChoiceField(
        queryset=File.objects.filter(category=FILE_TYPE_IMAGE), required=False,
        widget=forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"})
    )
    routedata_audio = forms.ModelChoiceField(
        queryset=File.objects.filter(category=FILE_TYPE_AUDIO), required=False,
        widget=forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"})
    )

    class Meta:
        model = RoutePart
        exclude = ["order", "route"]  # order en route zetten we zelf
        widgets = {
            "name": forms.TextInput(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "route_type": forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "routepart_zoom": forms.CheckboxInput(attrs={"class":"h-4 w-4"}),
            "routepart_fullscreen": forms.CheckboxInput(attrs={"class":"h-4 w-4"}),
            "final": forms.CheckboxInput(attrs={"class":"h-4 w-4"}),
        }