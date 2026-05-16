from django import forms
from django.core.exceptions import ValidationError


INPUT_CSS = "w-full rounded-lg border px-3 py-2"
TEXTAREA_CSS = "w-full rounded-lg border px-3 py-2"


class _RegistrationBase(forms.Form):
    """Shared: bind the form to an edition and reject e-mail addresses that
    are already registered for that edition (prevents silent duplicate
    sign-ups and gives the user a clear message instead of a 500)."""

    def __init__(self, *args, edition=None, **kwargs):
        self.edition = edition
        super().__init__(*args, **kwargs)

    def clean_contact_email(self):
        email = self.cleaned_data.get("contact_email")
        if (
            email
            and self.edition
            and self.edition.teams.filter(contact_email__iexact=email).exists()
        ):
            raise ValidationError(
                "Dit e-mailadres is al aangemeld voor deze editie."
            )
        return email


class QuickRegistrationForm(_RegistrationBase):
    """Quick registration: name + email only."""

    contact_name = forms.CharField(
        label="Naam",
        max_length=100,
        widget=forms.TextInput(attrs={"class": INPUT_CSS}),
    )
    contact_email = forms.EmailField(
        label="E-mailadres",
        widget=forms.EmailInput(attrs={"class": INPUT_CSS}),
    )


class ExtendedRegistrationForm(_RegistrationBase):
    """Extended registration: full team sign-up form."""

    contact_name = forms.CharField(
        label="Naam contactpersoon",
        max_length=100,
        widget=forms.TextInput(attrs={"class": INPUT_CSS}),
    )
    contact_address = forms.CharField(
        label="Adres contactpersoon",
        widget=forms.Textarea(attrs={"class": TEXTAREA_CSS, "rows": 2}),
    )
    contact_phone = forms.CharField(
        label="Telefoonnr. contactpersoon",
        max_length=100,
        widget=forms.TextInput(attrs={"class": INPUT_CSS}),
    )
    contact_email = forms.EmailField(
        label="E-mailadres contactpersoon",
        widget=forms.EmailInput(attrs={"class": INPUT_CSS}),
    )
    team_name = forms.CharField(
        label="Naam koppel/troppel (teamnaam)",
        max_length=255,
        widget=forms.TextInput(attrs={"class": INPUT_CSS}),
    )
    member_names = forms.CharField(
        label="Namen koppel-/troppelgenoten",
        widget=forms.Textarea(attrs={"class": TEXTAREA_CSS, "rows": 3}),
    )
    remarks = forms.CharField(
        label="Vragen/opmerkingen",
        required=False,
        widget=forms.Textarea(attrs={"class": TEXTAREA_CSS, "rows": 3}),
    )
