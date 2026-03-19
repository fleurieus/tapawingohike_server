from django import forms


INPUT_CSS = "w-full rounded-lg border px-3 py-2"
TEXTAREA_CSS = "w-full rounded-lg border px-3 py-2"


class QuickRegistrationForm(forms.Form):
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


class ExtendedRegistrationForm(forms.Form):
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
