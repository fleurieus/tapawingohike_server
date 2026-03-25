from django import forms
from django.contrib.auth.models import User
from server.apps.dashboard.models import Destination, Edition, Organization
from server.apps.dashboard.models import Bundle, Route, RoutePart, File, Destination
from server.apps.dashboard.constants import FILE_TYPE_IMAGE, FILE_TYPE_AUDIO

INPUT_CLASSES = "w-full rounded-lg border px-3 py-2"


class UserManagementForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    first_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    last_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": INPUT_CLASSES}),
    )
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        required=False,
        empty_label="Geen (superadmin)",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )
    is_active = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASSES, "placeholder": "Laat leeg om niet te wijzigen"}),
    )

    def __init__(self, *args, editing_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._editing_user = editing_user
        if not editing_user:
            # New user: password is required
            self.fields["password"].required = True
            self.fields["password"].widget.attrs.pop("placeholder", None)

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username)
        if self._editing_user:
            qs = qs.exclude(pk=self._editing_user.pk)
        if qs.exists():
            raise forms.ValidationError("Deze gebruikersnaam is al in gebruik.")
        return username


class EditionRegistrationForm(forms.ModelForm):
    class Meta:
        model = Edition
        fields = ["registration_mode", "registration_confirmation_text", "messaging_enabled"]
        widgets = {
            "registration_mode": forms.Select(
                attrs={"class": "w-full rounded-lg border px-3 py-2"}
            ),
            "registration_confirmation_text": forms.Textarea(
                attrs={"class": "w-full rounded-lg border px-3 py-2", "rows": 5}
            ),
            "messaging_enabled": forms.CheckboxInput(
                attrs={"class": "rounded border-slate-300 text-slate-900 focus:ring-slate-500"}
            ),
        }

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
        fields = ["name", "edition", "date"]
        widgets = {
            "name": forms.TextInput(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "edition": forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "date": forms.DateInput(attrs={"type": "date", "class":"border rounded px-2 py-1 w-full"}, format="%Y-%m-%d"),
        }

class BundleForm(forms.ModelForm):
    class Meta:
        model = Bundle
        exclude = ["route"]  # route zetten we zelf
        widgets = {
            "name": forms.TextInput(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "browse_mode": forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
            "linear_upcoming_mode": forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
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
    new_image_upload = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class":"border rounded px-2 py-1 w-full", "accept":"image/*"}),
        label="Of upload nieuw (afbeelding)",
    )
    new_audio_upload = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class":"border rounded px-2 py-1 w-full", "accept":"audio/*"}),
        label="Of upload nieuw (audio)",
    )
    bundle = forms.ModelChoiceField(
        queryset=Bundle.objects.none(), required=False,
        widget=forms.Select(attrs={"class":"border rounded px-2 py-1 w-full"}),
        label="Bundel",
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

    def __init__(self, *args, route=None, **kwargs):
        super().__init__(*args, **kwargs)
        if route:
            self.fields["bundle"].queryset = Bundle.objects.filter(route=route)