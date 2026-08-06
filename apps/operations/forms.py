from django import forms


class CheckpointCommandForm(forms.Form):
    idempotency_key = forms.CharField(
        min_length=8,
        max_length=255,
        widget=forms.HiddenInput,
    )


class OutboxRetryForm(forms.Form):
    reason = forms.CharField(
        min_length=3,
        max_length=100,
        initial="manual_operational_retry",
        label="Retry reason",
    )
