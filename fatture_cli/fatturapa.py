"""FatturaPA v1.2.3 (FPR12) XML generation and XSD validation.

Builds an Italian electronic invoice (Fattura Elettronica ordinaria, TipoDocumento
TD01) from a Fatture in Cloud invoice payload, and validates the result against
the official XSD bundled under `fatture_cli/schemas/`.

Schema source: https://www.fatturapa.gov.it/ — `Schema_VFPR12_v1.2.3.xsd`.

The XSD imports `xmldsig-core-schema.xsd`; the bundled FatturaPA XSD has been
patched to reference the local copy by relative path so validation works
fully offline.

The FatturaPA schema declares no `elementFormDefault`, which means it defaults
to "unqualified": only the root `FatturaElettronica` element is in the FPR12
namespace, while every descendant lives in NO namespace. We replicate that
exactly when building.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from lxml import etree

# ---------------------------------------------------------------------------
# Namespaces / constants
# ---------------------------------------------------------------------------

FPR12_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

SCHEMA_LOCATION = (
    f"{FPR12_NS} "
    "http://www.fatturapa.gov.it/sdi/fatturapa/documenti/Schema_VFPR12_v1.2.3.xsd"
)

_SCHEMA_DIR = Path(__file__).parent / "schemas"
_FATTURAPA_XSD_PATH = _SCHEMA_DIR / "FatturaPA_v1.2.3.xsd"

_schema_cache: etree.XMLSchema | None = None


# ---------------------------------------------------------------------------
# Number / string helpers
# ---------------------------------------------------------------------------


def _money(value: Any) -> str:
    """Format a monetary amount with exactly two decimals (FatturaPA money type)."""
    if value is None:
        value = 0
    q = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def _quantity(value: Any) -> str:
    """Format a quantity (FatturaPA allows 2-8 decimals — we use 2)."""
    if value is None:
        value = 1
    q = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def _rate(value: Any) -> str:
    """Format a VAT rate (AliquotaIVA: 2 decimals required)."""
    if value is None:
        value = 0
    q = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def _parse_vat(vat: str | None) -> tuple[str, str] | None:
    """Split a VAT id into (country, code). Returns None if no usable id.

    FatturaPA's IdFiscaleIVA requires both IdPaese (ISO 3166 alpha-2) and
    IdCodice. A bare numeric VAT (e.g. "01234567890") is assumed Italian.
    """
    if not vat:
        return None
    cleaned = "".join(vat.split()).upper()
    if not cleaned:
        return None
    if len(cleaned) >= 2 and cleaned[:2].isalpha():
        return cleaned[:2], cleaned[2:]
    return "IT", cleaned


def _e(parent: etree._Element, tag: str, text: Any = None) -> etree._Element:
    """SubElement helper that writes text only when it has content."""
    el = etree.SubElement(parent, tag)
    if text is not None and str(text) != "":
        el.text = str(text)
    return el


def _addr_field(address: Any, key: str, default: str = "") -> str:
    """Read a field from either a nested address dict or the flat FiC entity shape."""
    if isinstance(address, dict) and key in address:
        return str(address.get(key) or default)
    return default


# ---------------------------------------------------------------------------
# Subtree builders
# ---------------------------------------------------------------------------


def _build_anagrafici(parent: etree._Element, party: dict, *, role: str) -> None:
    """Populate DatiAnagrafici for either CedentePrestatore or CessionarioCommittente.

    The XSD declares DatiAnagrafici as a strict sequence:
    `IdFiscaleIVA?, CodiceFiscale?, Anagrafica, …` — and at least one of
    IdFiscaleIVA / CodiceFiscale must be present, so we must always emit one
    BEFORE Anagrafica. The seller (CedentePrestatore) further requires
    IdFiscaleIVA (no CodiceFiscale-only path) and a RegimeFiscale.
    """
    anag = etree.SubElement(parent, "DatiAnagrafici")

    vat = _parse_vat(party.get("vat_number"))
    tax_code = (party.get("tax_code") or "").strip()

    if role == "seller":
        # Sellers MUST have IdFiscaleIVA. If the upstream record is missing it,
        # emit a placeholder so the document remains structurally valid — the
        # human-readable name still travels via Anagrafica/Denominazione.
        if vat is None:
            vat = ("IT", "00000000000")
        idiva = etree.SubElement(anag, "IdFiscaleIVA")
        _e(idiva, "IdPaese", vat[0])
        _e(idiva, "IdCodice", vat[1])
        # CodiceFiscale is optional, include it only when distinct from VAT.
        if tax_code and tax_code != vat[1]:
            _e(anag, "CodiceFiscale", tax_code)
    else:
        # Buyer: pick exactly one identifier. Order of preference matches the
        # XSD sequence — IdFiscaleIVA first, then CodiceFiscale. Italian
        # individuals usually have only a tax_code (16-char codice fiscale),
        # which belongs in CodiceFiscale, not IdFiscaleIVA.
        if vat is not None:
            idiva = etree.SubElement(anag, "IdFiscaleIVA")
            _e(idiva, "IdPaese", vat[0])
            _e(idiva, "IdCodice", vat[1])
        elif tax_code:
            _e(anag, "CodiceFiscale", tax_code)
        else:
            idiva = etree.SubElement(anag, "IdFiscaleIVA")
            _e(idiva, "IdPaese", "IT")
            _e(idiva, "IdCodice", "00000000000")

    ana = etree.SubElement(anag, "Anagrafica")
    name = (party.get("name") or "").strip() or "N/D"
    _e(ana, "Denominazione", name)

    if role == "seller":
        # RF01 = ordinario. Sellers MUST declare a regime; default if absent.
        _e(anag, "RegimeFiscale", party.get("regime_fiscale") or "RF01")


def _build_sede(parent: etree._Element, party: dict) -> None:
    """Populate the Sede element from either a nested `address` dict or flat FiC fields."""
    sede = etree.SubElement(parent, "Sede")
    address = party.get("address") if isinstance(party.get("address"), dict) else None

    indirizzo = (
        _addr_field(address, "street")
        or party.get("address_street")
        or "N/D"
    )
    cap = (
        _addr_field(address, "postal_code")
        or party.get("address_postal_code")
        or "00000"
    )
    comune = (
        _addr_field(address, "city")
        or party.get("address_city")
        or "N/D"
    )
    provincia = (
        _addr_field(address, "province")
        or party.get("address_province")
        or ""
    )
    nazione = (
        _addr_field(address, "country")
        or party.get("country")
        or "IT"
    )

    _e(sede, "Indirizzo", str(indirizzo)[:60])
    _e(sede, "CAP", str(cap)[:5].zfill(5))
    _e(sede, "Comune", str(comune)[:60])
    if provincia:
        _e(sede, "Provincia", str(provincia)[:2].upper())
    _e(sede, "Nazione", str(nazione)[:2].upper())


def _build_dati_trasmissione(parent: etree._Element, company: dict, invoice: dict) -> None:
    dt = etree.SubElement(parent, "DatiTrasmissione")
    vat = _parse_vat(company.get("vat_number")) or (
        "IT",
        (company.get("tax_code") or "00000000000"),
    )
    idt = etree.SubElement(dt, "IdTrasmittente")
    _e(idt, "IdPaese", vat[0])
    _e(idt, "IdCodice", vat[1])

    # ProgressivoInvio: 1-10 alnum chars. We use the invoice id, zero-padded.
    progressivo = str(invoice.get("id") or "1")[:10]
    _e(dt, "ProgressivoInvio", progressivo)
    _e(dt, "FormatoTrasmissione", "FPR12")
    # 0000000 = transmission via PEC or recipient code unknown.
    _e(dt, "CodiceDestinatario", invoice.get("codice_destinatario") or "0000000")


def _build_dettaglio_linee(parent: etree._Element, items: list[dict]) -> list[dict]:
    """Emit DettaglioLinee entries; return the (rate -> imponibile) groupings.

    Each line's PrezzoTotale is qty * net_price, NOT including VAT. The
    DatiRiepilogo block summarises taxable amounts and computed tax per rate.
    """
    groups: dict[str, Decimal] = {}
    for idx, item in enumerate(items or [], start=1):
        line = etree.SubElement(parent, "DettaglioLinee")
        _e(line, "NumeroLinea", idx)

        desc = item.get("name") or item.get("description") or "Voce"
        _e(line, "Descrizione", str(desc)[:1000])

        qty_raw = item.get("qty")
        net_price_raw = item.get("net_price") or 0
        qty_dec = Decimal(str(qty_raw if qty_raw is not None else 1))
        unit_dec = Decimal(str(net_price_raw))
        total_dec = (qty_dec * unit_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        _e(line, "Quantita", _quantity(qty_dec))
        _e(line, "PrezzoUnitario", _money(unit_dec))
        _e(line, "PrezzoTotale", _money(total_dec))

        vat = item.get("vat") or {}
        rate_raw = vat.get("value") if isinstance(vat, dict) else None
        rate_key = _rate(rate_raw or 0)
        _e(line, "AliquotaIVA", rate_key)

        groups[rate_key] = groups.get(rate_key, Decimal("0")) + total_dec

    return [
        {"rate": rate, "imponibile": amount}
        for rate, amount in sorted(groups.items())
    ]


def _build_dati_riepilogo(parent: etree._Element, groups: list[dict]) -> None:
    """One DatiRiepilogo per VAT rate. Imposta = imponibile * rate / 100."""
    if not groups:
        groups = [{"rate": "0.00", "imponibile": Decimal("0")}]

    for g in groups:
        riep = etree.SubElement(parent, "DatiRiepilogo")
        rate = Decimal(g["rate"])
        imponibile = Decimal(g["imponibile"])
        imposta = (imponibile * rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        _e(riep, "AliquotaIVA", _rate(rate))
        if rate == 0:
            # Schema requires Natura when AliquotaIVA == 0. N1 = escluse ex art. 15.
            _e(riep, "Natura", "N1")
        _e(riep, "ImponibileImporto", _money(imponibile))
        _e(riep, "Imposta", _money(imposta))
        _e(riep, "EsigibilitaIVA", "I")


def _build_dati_pagamento(parent: etree._Element, payments: list[dict]) -> None:
    """Emit DatiPagamento. Always TP02 (pagamento completo) for the body shape.

    Each FiC payments_list entry becomes a DettaglioPagamento. Status mapping:
    "paid" sets DataRiscossione; otherwise we just give due_date and amount.
    """
    if not payments:
        return
    block = etree.SubElement(parent, "DatiPagamento")
    _e(block, "CondizioniPagamento", "TP02")
    for p in payments:
        d = etree.SubElement(block, "DettaglioPagamento")
        # MP05 = bonifico. Real mapping would look at payment_method.type;
        # MP05 is the safe fallback the SDI accepts for most cases.
        _e(d, "ModalitaPagamento", "MP05")
        if p.get("due_date"):
            _e(d, "DataScadenzaPagamento", p["due_date"])
        _e(d, "ImportoPagamento", _money(p.get("amount") or 0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_fattura_xml(invoice: dict, company: dict) -> str:
    """Build a FatturaPA v1.2.3 (FPR12, TD01) XML document.

    `invoice` is the raw `data` payload returned by FiC's
    `GET /c/{company_id}/issued_documents/{id}` — i.e. with nested `entity`,
    `items_list`, `payments_list`, `amount_net`, `amount_gross`, etc.

    `company` is the seller's profile (from `/user/companies` or the company
    info endpoint). Expected keys: `name`, `vat_number`, `tax_code`,
    `address` (dict) or flat `address_*` fields, optional `regime_fiscale`.

    Returns the XML as a UTF-8 decoded string with the XML declaration on
    the first line. Caller is responsible for choosing a filename (the
    canonical pattern is `IT{vat}_{progressive}.xml`).
    """
    nsmap = {"p": FPR12_NS, "ds": DS_NS, "xsi": XSI_NS}
    root = etree.Element(f"{{{FPR12_NS}}}FatturaElettronica", nsmap=nsmap)
    root.set("versione", "FPR12")
    root.set(f"{{{XSI_NS}}}schemaLocation", SCHEMA_LOCATION)

    # ---------------- Header ----------------
    header = etree.SubElement(root, "FatturaElettronicaHeader")
    _build_dati_trasmissione(header, company, invoice)

    cedente = etree.SubElement(header, "CedentePrestatore")
    _build_anagrafici(cedente, company, role="seller")
    _build_sede(cedente, company)

    entity = invoice.get("entity") or {}
    cessionario = etree.SubElement(header, "CessionarioCommittente")
    _build_anagrafici(cessionario, entity, role="buyer")
    _build_sede(cessionario, entity)

    # ---------------- Body ----------------
    body = etree.SubElement(root, "FatturaElettronicaBody")

    dati_gen = etree.SubElement(body, "DatiGenerali")
    dgd = etree.SubElement(dati_gen, "DatiGeneraliDocumento")
    _e(dgd, "TipoDocumento", "TD01")
    _e(dgd, "Divisa", (invoice.get("currency") or {}).get("id") or "EUR")
    _e(dgd, "Data", invoice.get("date"))
    number = invoice.get("number")
    numeration = invoice.get("numeration")
    full_number = f"{number}{numeration}" if numeration else str(number or "1")
    _e(dgd, "Numero", full_number)
    _e(dgd, "ImportoTotaleDocumento", _money(invoice.get("amount_gross") or 0))

    beni = etree.SubElement(body, "DatiBeniServizi")
    groups = _build_dettaglio_linee(beni, invoice.get("items_list") or [])
    _build_dati_riepilogo(beni, groups)

    _build_dati_pagamento(body, invoice.get("payments_list") or [])

    xml_bytes = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
    return xml_bytes.decode("utf-8")


def _load_schema() -> etree.XMLSchema:
    """Compile the bundled XSD once and cache it."""
    global _schema_cache
    if _schema_cache is None:
        # `parse(filename)` resolves the xs:import schemaLocation relative to
        # the XSD's own directory, which is exactly where xmldsig-core-schema.xsd
        # sits — so no resolver or network access is needed.
        xsd_doc = etree.parse(str(_FATTURAPA_XSD_PATH))
        _schema_cache = etree.XMLSchema(xsd_doc)
    return _schema_cache


def validate_fattura_xml(xml_string: str) -> list[str]:
    """Validate an XML string against the bundled FatturaPA XSD.

    Returns a list of human-readable error messages — empty when the document
    is valid. Caller decides whether to raise or report.
    """
    try:
        doc = etree.fromstring(xml_string.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return [f"XML syntax error: {exc}"]

    schema = _load_schema()
    if schema.validate(doc):
        return []
    return [
        f"line {err.line}: {err.message}"
        for err in schema.error_log
    ]
