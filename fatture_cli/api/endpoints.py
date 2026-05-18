"""Fatture in Cloud API endpoint constants.

Reference: https://developers.fattureincloud.it/
"""

API_BASE_URL = "https://api-v2.fattureincloud.it"

OAUTH_AUTHORIZE_URL = "https://api-v2.fattureincloud.it/oauth/authorize"
OAUTH_TOKEN_URL = "https://api-v2.fattureincloud.it/oauth/token"

DEFAULT_SCOPES = [
    "entity.clients:r",
    "entity.clients:a",
    "entity.suppliers:r",
    "entity.suppliers:a",
    "products:r",
    "products:a",
    "issued_documents.invoices:r",
    "issued_documents.invoices:a",
    "received_documents:r",
    "received_documents:a",
    "settings:r",
]

USER_INFO = "/user/info"
USER_COMPANIES = "/user/companies"

INVOICES_LIST = "/c/{company_id}/issued_documents"
INVOICE_DETAIL = "/c/{company_id}/issued_documents/{document_id}"

CLIENTS_LIST = "/c/{company_id}/entities/clients"
CLIENT_DETAIL = "/c/{company_id}/entities/clients/{client_id}"

PRODUCTS_LIST = "/c/{company_id}/products"
PRODUCT_DETAIL = "/c/{company_id}/products/{product_id}"
