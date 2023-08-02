from django.core.exceptions import ValidationError


class FinalDestinationValidationMixin:
    def clean(self):
        if self.final and self.destinations.exists():
            raise ValidationError(
                "Verwijder eerst de Bestemming(en) voordat je het vinkje 'final' aanvinkt."
            )

        return super().clean()
