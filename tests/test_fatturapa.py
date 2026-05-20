"""Tests for FatturaPA XML generation and XSD validation."""

from __future__ import annotations

import pytest
from lxml import etree

from fatture_cli.fatturapa import (
    FPR12_NS,
    build_fattura_xml,
    validate_fattura_xml,
)


@pytest.fixture
def company() -> dict:
    return {
        "name": "Mia Azienda S.r.l.",
        "vat_number": "IT01234567890",
        "tax_code": "01234567890",
        "address_street": "Via Roma 1",
        "address_postal_code": "00100",
        "address_city": "Roma",
        "address_province": "RM",
        "country": "IT",
    }


@pytest.fixture
def invoice() -> dict:
    return {
        "id": 526346861,
        "number": 1,
        "date": "2026-05-19",
        "entity": {
            "name": "Cliente S.r.l.",
            "vat_number": "IT09876543210",
            "address_street": "Via Milano 10",
            "address_postal_code": "20121",
            "address_city": "Milano",
            "address_province": "MI",
            "country": "IT",
        },
        "items_list": [
            {"name": "Consulenza maggio", "qty": 1, "net_price": 1000, "vat": {"value": 22}},
        ],
        "amount_net": 1000,
        "amount_gross": 1220,
        "payments_list": [
            {"due_date": "2026-06-19", "amount": 1220, "status": "not_paid"},
        ],
    }


def _parse(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def test_build_fattura_xml_produces_valid_xml(invoice: dict, company: dict) -> None:
    xml = build_fattura_xml(invoice, company)
    assert validate_fattura_xml(xml) == []


def test_root_element_is_fpr12(invoice: dict, company: dict) -> None:
    root = _parse(build_fattura_xml(invoice, company))
    assert root.tag == f"{{{FPR12_NS}}}FatturaElettronica"
    assert root.get("versione") == "FPR12"


def test_xml_contains_tipo_documento_td01(invoice: dict, company: dict) -> None:
    xml = build_fattura_xml(invoice, company)
    root = _parse(xml)
    # Body elements are in NO namespace per the FatturaPA schema (no elementFormDefault).
    tipo = root.find(".//TipoDocumento")
    assert tipo is not None
    assert tipo.text == "TD01"


def test_seller_vat_split_into_country_and_code(invoice: dict, company: dict) -> None:
    root = _parse(build_fattura_xml(invoice, company))
    cedente = root.find(".//CedentePrestatore/DatiAnagrafici/IdFiscaleIVA")
    assert cedente is not None
    assert cedente.findtext("IdPaese") == "IT"
    assert cedente.findtext("IdCodice") == "01234567890"


def test_riepilogo_aggregates_lines_with_same_vat_rate(company: dict) -> None:
    """Two lines at 22% should collapse into a single DatiRiepilogo entry."""
    invoice = {
        "id": 1,
        "number": 1,
        "date": "2026-05-19",
        "entity": {
            "name": "Cliente",
            "vat_number": "IT09876543210",
            "address_street": "Via X",
            "address_postal_code": "20121",
            "address_city": "Milano",
            "address_province": "MI",
            "country": "IT",
        },
        "items_list": [
            {"name": "A", "qty": 1, "net_price": 100, "vat": {"value": 22}},
            {"name": "B", "qty": 2, "net_price": 50, "vat": {"value": 22}},
        ],
        "amount_net": 200,
        "amount_gross": 244,
        "payments_list": [],
    }
    root = _parse(build_fattura_xml(invoice, company))
    rieps = root.findall(".//DatiRiepilogo")
    assert len(rieps) == 1
    assert rieps[0].findtext("ImponibileImporto") == "200.00"
    # 200 * 22% = 44.00
    assert rieps[0].findtext("Imposta") == "44.00"


def test_validate_catches_missing_required_fields() -> None:
    """An XML missing mandatory FatturaPA elements must report XSD errors."""
    bad = """<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12"
    xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione/>
  </FatturaElettronicaHeader>
</p:FatturaElettronica>
"""
    errors = validate_fattura_xml(bad)
    assert errors, "expected validator to flag the empty document"
    # The first missing child reported by libxml on DatiTrasmissione is IdTrasmittente.
    assert any("IdTrasmittente" in e for e in errors)


def test_validate_reports_xml_syntax_error() -> None:
    errors = validate_fattura_xml("<not-xml")
    assert errors
    assert "XML syntax error" in errors[0]


def test_seller_without_vat_gets_placeholder_idfiscaleiva(invoice: dict) -> None:
    """Sellers MUST emit IdFiscaleIVA — placeholder when the source has none."""
    bare_company = {
        "name": "Mia Azienda",
        "address_street": "Via Roma 1",
        "address_postal_code": "00100",
        "address_city": "Roma",
        "address_province": "RM",
        "country": "IT",
    }
    xml = build_fattura_xml(invoice, bare_company)
    assert validate_fattura_xml(xml) == []
    root = _parse(xml)
    idiva = root.find(".//CedentePrestatore/DatiAnagrafici/IdFiscaleIVA")
    assert idiva is not None
    assert idiva.findtext("IdPaese") == "IT"
    assert idiva.findtext("IdCodice") == "00000000000"


def test_buyer_with_only_tax_code_uses_codice_fiscale(company: dict) -> None:
    """Italian individuals carry a 16-char codice fiscale; map it to CodiceFiscale."""
    invoice = {
        "id": 1,
        "number": 1,
        "date": "2026-05-19",
        "entity": {
            "name": "Mario Rossi",
            "tax_code": "RSSMRA80A01H501U",
            "address_street": "Via X",
            "address_postal_code": "20121",
            "address_city": "Milano",
            "address_province": "MI",
            "country": "IT",
        },
        "items_list": [
            {"name": "Servizio", "qty": 1, "net_price": 100, "vat": {"value": 22}},
        ],
        "amount_net": 100,
        "amount_gross": 122,
        "payments_list": [],
    }
    xml = build_fattura_xml(invoice, company)
    assert validate_fattura_xml(xml) == []
    root = _parse(xml)
    anag = root.find(".//CessionarioCommittente/DatiAnagrafici")
    assert anag is not None
    assert anag.find("IdFiscaleIVA") is None
    assert anag.findtext("CodiceFiscale") == "RSSMRA80A01H501U"


def test_buyer_without_any_identifier_gets_placeholder(company: dict) -> None:
    """Missing both vat_number and tax_code must still produce a valid document."""
    invoice = {
        "id": 1,
        "number": 1,
        "date": "2026-05-19",
        "entity": {
            "name": "Cliente Anonimo",
            "address_street": "Via X",
            "address_postal_code": "20121",
            "address_city": "Milano",
            "address_province": "MI",
            "country": "IT",
        },
        "items_list": [
            {"name": "Servizio", "qty": 1, "net_price": 100, "vat": {"value": 22}},
        ],
        "amount_net": 100,
        "amount_gross": 122,
        "payments_list": [],
    }
    xml = build_fattura_xml(invoice, company)
    assert validate_fattura_xml(xml) == []
    root = _parse(xml)
    idiva = root.find(".//CessionarioCommittente/DatiAnagrafici/IdFiscaleIVA")
    assert idiva is not None
    assert idiva.findtext("IdCodice") == "00000000000"


def test_zero_vat_rate_gets_natura(company: dict) -> None:
    """A 0% line is invalid without a Natura code — the builder must add one."""
    invoice = {
        "id": 1,
        "number": 1,
        "date": "2026-05-19",
        "entity": {
            "name": "Cliente",
            "tax_code": "RSSMRA80A01H501U",
            "address_street": "Via X",
            "address_postal_code": "20121",
            "address_city": "Milano",
            "address_province": "MI",
            "country": "IT",
        },
        "items_list": [
            {"name": "Esente", "qty": 1, "net_price": 100, "vat": {"value": 0}},
        ],
        "amount_net": 100,
        "amount_gross": 100,
        "payments_list": [],
    }
    xml = build_fattura_xml(invoice, company)
    assert validate_fattura_xml(xml) == []
    root = _parse(xml)
    riep = root.find(".//DatiRiepilogo")
    assert riep is not None
    assert riep.findtext("Natura") is not None
