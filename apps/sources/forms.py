from __future__ import annotations

import ipaddress
from typing import Any

from django import forms

from apps.sources.policy import SourcePolicyError, normalize_hostname


class PublicSourceSubmissionForm(forms.Form):
    requested_url = forms.URLField(
        max_length=4096,
        label="Public source URL",
        help_text="Public HTTPS job page, careers endpoint, or first-party source.",
    )
    company_name = forms.CharField(
        max_length=500,
        required=False,
        help_text="Optional source-backed company hint; it remains provisional.",
    )
    company_domain = forms.CharField(
        max_length=255,
        required=False,
        help_text="Optional company domain hint, never inferred from a generic ATS host.",
    )
    public_source_confirmed = forms.BooleanField(
        label="I confirm this URL is public, ungated, and appropriate to retrieve.",
    )
    idempotency_key = forms.CharField(max_length=255, widget=forms.HiddenInput)

    def clean_company_domain(self) -> str:
        value = self.cleaned_data.get("company_domain", "").strip()
        if not value:
            return ""
        try:
            hostname_ascii, _hostname_unicode = normalize_hostname(value)
            ipaddress.ip_address(hostname_ascii)
        except ValueError:
            return hostname_ascii
        except SourcePolicyError as exc:
            raise forms.ValidationError(exc.safe_message) from exc
        raise forms.ValidationError("A company domain must be a hostname, not an IP address.")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if cleaned.get("company_domain") and not cleaned.get("company_name"):
            self.add_error("company_name", "Provide a company name with a company-domain hint.")
        return cleaned
