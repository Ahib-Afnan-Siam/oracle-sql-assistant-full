# ERP R12 Vector Store Chroma
# Vector store helpers for ChromaDB (with query-time synonym expansion)
import logging
import os
from typing import List, Dict

import chromadb
from chromadb.config import Settings

# ---- Telemetry handling with version compatibility ----
try:
    from chromadb.telemetry.posthog import Posthog
    # For older versions of ChromaDB
    def safe_capture(self, *args, **kwargs):
        # Newer Chroma calls capture with variable args; just swallow.
        return None
    Posthog.capture = safe_capture
except ImportError:
    # For newer versions of ChromaDB where this import doesn't exist
    pass

# Disable telemetry
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from app.embeddings import get_embedding

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

# =========================
# Environment switches
# =========================
ENABLE_QUERY_SYNONYMS = os.getenv("ENABLE_QUERY_SYNONYMS", "true").lower() == "true"

# =========================
# Per-DB Chroma client
# =========================
def get_chroma_client(selected_db: str):
    return chromadb.PersistentClient(
        path=f"chroma_storage/{selected_db}",
        settings=Settings(anonymized_telemetry=False)
    )

# =========================
# Enhanced synonyms for ERP R12 tables and columns
# =========================
COLUMN_SYNONYMS = {
    # HR_OPERATING_UNITS table columns
    "BUSINESS_GROUP_ID": ["business group id", "bg id", "business group identifier", "business_group_id", "business group", "bg", "business group identifier"],
    "ORGANIZATION_ID": ["organization id", "org id", "organization identifier", "org_id", "operating unit id", "ou id", "org id", "operating unit identifier"],
    "NAME": ["name", "operating unit name", "ou name", "business unit name", "unit name", "operating unit", "organization name", "org name"],
    "DATE_FROM": ["date from", "start date", "valid from", "effective from", "begin date", "from date"],
    "DATE_TO": ["date to", "end date", "valid to", "effective to", "finish date", "expiration date", "to date"],
    "SHORT_CODE": ["short code", "code", "abbreviation", "short name", "org code", "organization code"],
    "SET_OF_BOOKS_ID": ["set of books id", "sob id", "ledger id", "accounting book id", "book id", "set of books", "books id", "ledger identifier"],
    "DEFAULT_LEGAL_CONTEXT_ID": ["default legal context id", "legal entity id", "le id", "default legal entity", "legal context id", "legal context", "legal entity"],
    "USABLE_FLAG": ["usable flag", "is usable", "active flag", "enabled flag", "status", "currently usable", "usable", "currently active", "active operating unit", "working unit", "functional unit", "availability flag"],
    
    # ORG_ORGANIZATION_DEFINITIONS table columns
    "USER_DEFINITION_ENABLE_DATE": ["user definition enable date", "enable date", "activation date", "user enable date", "definition enable date"],
    "DISABLE_DATE": ["disable date", "deactivation date", "end date", "expiration date", "inactive date", "disabled date"],
    "ORGANIZATION_CODE": ["organization code", "org code", "org id", "organization id", "code", "short code"],
    "ORGANIZATION_NAME": ["organization name", "org name", "organization title", "org title", "name", "org name"],
    "CHART_OF_ACCOUNTS_ID": ["chart of accounts id", "coa id", "account structure id", "chart id", "accounts id"],
    "INVENTORY_ENABLED_FLAG": ["inventory enabled flag", "inventory enabled", "is inventory enabled", "inventory status", "inventory", "stock enabled", "inventory availability", "inventory flag"],
    "OPERATING_UNIT": ["operating unit", "ou", "operating unit id", "ou id", "org_id"],
    "LEGAL_ENTITY": ["legal entity", "le", "legal entity id", "le id", "legal context"],
    
    # MTL_ONHAND_QUANTITIES_DETAIL table columns
    "INVENTORY_ITEM_ID": ["inventory item id", "item id", "inventory id", "item"],
    "DATE_RECEIVED": ["date received", "received date", "receipt date", "items received"],
    "PRIMARY_TRANSACTION_QUANTITY": ["primary transaction quantity", "primary qty", "transaction quantity", "onhand quantity", "quantity on hand", "on-hand quantity"],
    "SUBINVENTORY_CODE": ["subinventory code", "subinv code", "subinventory", "subinv", "sub inventory"],
    "REVISION": ["revision", "rev"],
    "LOCATOR_ID": ["locator id", "location id", "locator"],
    "LOT_NUMBER": ["lot number", "lot", "batch number", "batch"],
    "COST_GROUP_ID": ["cost group id", "cost group"],
    "PROJECT_ID": ["project id", "project"],
    "TASK_ID": ["task id", "task"],
    "ONHAND_QUANTITIES_ID": ["onhand quantities id", "onhand id"],
    "CONTAINERIZED_FLAG": ["containerized flag", "containerized"],
    "IS_CONSIGNED": ["is consigned", "consigned flag", "consigned", "consigned inventory"],
    "LPN_ID": ["lpn id", "license plate number id", "license plate"],
    "STATUS_ID": ["status id", "status"],
    "MCC_CODE": ["mcc code", "material control code"],
    "CREATE_TRANSACTION_ID": ["create transaction id", "creation transaction id"],
    "UPDATE_TRANSACTION_ID": ["update transaction id", "last update transaction id"],
    "ORIG_DATE_RECEIVED": ["orig date received", "original date received"],
    "OWNING_ORGANIZATION_ID": ["owning organization id", "owner org id"],
    "PLANNING_ORGANIZATION_ID": ["planning organization id", "planning org id"],
    "TRANSACTION_UOM_CODE": ["transaction uom code", "uom code", "unit of measure code"],
    "TRANSACTION_QUANTITY": ["transaction quantity", "trans qty"],
    "SECONDARY_UOM_CODE": ["secondary uom code", "secondary unit of measure code"],
    "SECONDARY_TRANSACTION_QUANTITY": ["secondary transaction quantity", "secondary qty"],
    "OWNING_TP_TYPE": ["owning tp type", "owner third party type"],
    "PLANNING_TP_TYPE": ["planning tp type", "planning third party type"],
    "ORGANIZATION_TYPE": ["organization type", "org type"],
    
    # MTL_SECONDARY_INVENTORIES table columns
    "SECONDARY_INVENTORY_NAME": ["secondary inventory name", "subinventory name", "secondary inv name", "subinv name", "subinventory"],
    "DESCRIPTION": ["description", "desc"],
    "DISABLE_DATE": ["disable date", "deactivation date", "end date", "expiration date", "inactive date", "disabled date", "disabled subinventories"],
    "INVENTORY_ATP_CODE": ["inventory atp code", "atp code", "available to promise code"],
    "AVAILABILITY_TYPE": ["availability type", "availability"],
    "RESERVABLE_TYPE": ["reservable type", "reservable", "reservable indicator", "reservation allowed", "allow reservations"],
    "LOCATOR_TYPE": ["locator type", "locator"],
    "PICKING_ORDER": ["picking order", "pick order"],
    "MATERIAL_ACCOUNT": ["material account", "mat account"],
    "DEMAND_CLASS": ["demand class", "demand"],
    "SUBINVENTORY_USAGE": ["subinventory usage", "subinv usage"],
    "PICK_METHODOLOGY": ["pick methodology", "picking method"],
    "CARTONIZATION_FLAG": ["cartonization flag", "cartonization"],
    "DROPPING_ORDER": ["dropping order", "drop order"],
    "SUBINVENTORY_TYPE": ["subinventory type", "subinv type"],
    "PLANNING_LEVEL": ["planning level", "plan level"],
    "ENABLE_BULK_PICK": ["enable bulk pick", "bulk pick"],
    "ENABLE_LOCATOR_ALIAS": ["enable locator alias", "locator alias"],
    "ENFORCE_ALIAS_UNIQUENESS": ["enforce alias uniqueness", "alias uniqueness"],
    "ENABLE_OPP_CYC_COUNT": ["enable opp cyc count", "opportunistic cycle count"],
    "DEFAULT_COST_GROUP_ID": ["default cost group id", "cost group id", "default cost group"],
    "DEFAULT_COST_GROUP_ID": ["default cost group id", "cost group id", "default cost group"],
    
    # ERP R12 relationship terms
    "HR_OPERATING_UNITS": ["operating units", "business units", "org units", "ou table", "hr operating units", "hr ou", "operating unit table"],
    "ORG_ORGANIZATION_DEFINITIONS": ["organization definitions", "org definitions", "organizations", "org table", "org organization definitions", "org defs", "organization table"],
    "MTL_ONHAND_QUANTITIES_DETAIL": ["onhand quantities", "onhand inventory", "inventory quantities", "mtl onhand", "onhand detail", "items received", "inventory items"],
    "MTL_SECONDARY_INVENTORIES": ["secondary inventories", "subinventories", "sub inventory", "mtl secondary", "secondary inv", "subinv"],
    "MTL_DEMAND": ["material demand", "demand planning", "inventory demand", "mtl demand", "demand requirements"],
    "MTL_ITEM_LOCATIONS": ["item locations", "locator definitions", "warehouse storage", "physical locations", "inventory coordinates", "storage capacity", "subinventory locations"],
    "MTL_MATERIAL_STATUSES_B": ["material statuses", "inventory controls", "lot tracking", "serial tracking", "locator controls", "status configurations", "warehouse policies"],
    "MTL_RESERVATIONS": ["material reservations", "inventory allocation", "demand fulfillment", "supply chain tracking", "reservation quantities", "requirement dates", "supply sources", "demand sources"],
    "MTL_TRANSACTION_ACCOUNTS": ["transaction accounts", "inventory accounting", "transaction values", "currency conversions", "cost elements", "financial tracking", "gl integration", "account assignments"],
    "MTL_TRANSACTION_TYPES": ["transaction types", "inventory transactions", "transaction classification", "type definitions", "transaction controls", "business processes", "transaction actions"],
    "MTL_TXN_REQUEST_HEADERS": ["transaction requests", "move orders", "subinventory transfers", "inventory requests", "request headers", "transfer requests", "move order headers"],
    "MTL_TXN_REQUEST_LINES": ["transaction request lines", "move order lines", "inventory item tracking", "lot tracking", "delivery status", "quantity tracking", "line details"],
    "MTL_TXN_SOURCE_TYPES": ["transaction source types", "inventory sources", "source classification", "source definitions", "source controls", "business processes", "transaction sources"],
    "PO_DISTRIBUTIONS_ALL": ["purchase order distributions", "po distributions", "financial tracking", "project costing", "accounting distributions", "delivery management", "expenditure tracking"],
    "PO_HEADERS_ALL": ["purchase orders", "po headers", "supplier orders", "procurement tracking", "approval status", "purchase order numbers", "supplier information", "financial controls"],
    "PO_LINES_ALL": ["purchase order lines", "po lines", "line items", "item details", "order quantities", "unit prices", "line descriptions"],
    "PO_LINE_LOCATIONS_ALL": ["purchase order line locations", "po line locations", "shipment schedules", "delivery schedules", "receipt schedules", "line shipment details"],
    "PO_REQUISITION_HEADERS_ALL": ["requisition headers", "purchase requisitions", "requisition forms", "procurement requests", "requisition tracking", "approval workflows"],
    "PO_REQUISITION_LINES_ALL": ["requisition lines", "requisition items", "procurement line items", "requisition details", "item requisitions", "line item requests"],
    "PO_REQ_DISTRIBUTIONS_ALL": ["requisition distributions", "requisition accounting", "procurement distributions", "requisition financials", "distribution allocations"],
    "RCV_SHIPMENT_HEADERS": ["receiving shipment headers", "receipt headers", "shipment receipts", "incoming shipments", "goods receipts"],
    "RCV_SHIPMENT_LINES": ["receiving shipment lines", "receipt lines", "shipment items", "incoming shipment details", "goods receipt lines"],
    "RCV_TRANSACTIONS": ["receiving transactions", "receipt transactions", "goods receipt transactions", "receiving entries", "receipt entries"],
    "OE_ORDER_HEADERS_ALL": ["order headers", "sales orders", "customer orders", "order management", "sales order headers"],
    "OE_ORDER_LINES_ALL": ["order lines", "sales order lines", "customer order lines", "order items", "line items"],
    "OE_TRANSACTION_TYPES_ALL": ["transaction types", "order transaction types", "sales transaction types", "customer transaction types", "transaction categories"],
    "FND_LOOKUP_VALUES": ["lookup values", "reference data", "code translations", "system lookups", "application codes"],
    "FND_LOOKUP_VALUES_VL": ["lookup views", "reference data views", "code meanings", "system references", "application lookups"],
    "WSH_DELIVERY_ASSIGNMENTS": ["delivery assignments", "shipment assignments", "delivery linking", "shipment linking", "wsh delivery assignments", "delivery assignment table"],
    "WSH_DELIVERY_DETAILS": ["delivery details", "shipment details", "delivery lines", "shipment lines", "wsh delivery details", "delivery detail table"],
    
# HR_LOCATIONS_ALL table columns
    "LOCATION_ID": ["location id", "loc id", "location identifier", "hr location id"],
    "LOCATION_CODE": ["location code", "loc code", "location identifier code"],
    "BUSINESS_GROUP_ID": ["business group id", "bg id", "business group identifier"],
    "DESCRIPTION": ["description", "desc", "location description"],
    "SHIP_TO_LOCATION_ID": ["ship to location id", "ship to loc id", "shipping location id"],
    "SHIP_TO_SITE_FLAG": ["ship to site flag", "ship to site", "shipping site flag"],
    "RECEIVING_SITE_FLAG": ["receiving site flag", "receiving site", "receipt site flag"],
    "BILL_TO_SITE_FLAG": ["bill to site flag", "bill to site", "billing site flag"],
    "IN_ORGANIZATION_FLAG": ["in organization flag", "in org flag", "within organization flag"],
    "OFFICE_SITE_FLAG": ["office site flag", "office site", "office location flag"],
    "DESIGNATED_RECEIVER_ID": ["designated receiver id", "designated receiver", "receiver id"],
    "INVENTORY_ORGANIZATION_ID": ["inventory organization id", "inventory org id", "inv org id"],
    "TAX_NAME": ["tax name", "tax"],
    "INACTIVE_DATE": ["inactive date", "deactivation date", "end date", "expiration date"],
    "STYLE": ["style"],
    "ADDRESS_LINE_1": ["address line 1", "address 1", "street address", "primary address"],
    "ADDRESS_LINE_2": ["address line 2", "address 2", "secondary address"],
    "ADDRESS_LINE_3": ["address line 3", "address 3", "tertiary address"],
    "TOWN_OR_CITY": ["town or city", "town", "city", "municipality"],
    "COUNTRY": ["country"],
    "POSTAL_CODE": ["postal code", "zip code", "postcode"],
    "REGION_1": ["region 1", "region one", "state", "province"],
    "REGION_2": ["region 2", "region two", "county"],
    "REGION_3": ["region 3", "region three"],
    "TELEPHONE_NUMBER_1": ["telephone number 1", "phone number 1", "tel 1", "phone 1"],
    "TELEPHONE_NUMBER_2": ["telephone number 2", "phone number 2", "tel 2", "phone 2"],
    "TELEPHONE_NUMBER_3": ["telephone number 3", "phone number 3", "tel 3", "phone 3"],
    "LOC_INFORMATION13": ["loc information 13", "location info 13"],
    "LOC_INFORMATION14": ["loc information 14", "location info 14"],
    "LOC_INFORMATION15": ["loc information 15", "location info 15"],
    "LOC_INFORMATION16": ["loc information 16", "location info 16"],
    "LOC_INFORMATION17": ["loc information 17", "location info 17"],
    "ATTRIBUTE_CATEGORY": ["attribute category", "flexfield category"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "ATTRIBUTE16": ["attribute 16", "flexfield attribute 16"],
    "ATTRIBUTE17": ["attribute 17", "flexfield attribute 17"],
    "ATTRIBUTE18": ["attribute 18", "flexfield attribute 18"],
    "ATTRIBUTE19": ["attribute 19", "flexfield attribute 19"],
    "ATTRIBUTE20": ["attribute 20", "flexfield attribute 20"],
    "GLOBAL_ATTRIBUTE_CATEGORY": ["global attribute category", "global flexfield category"],
    "GLOBAL_ATTRIBUTE1": ["global attribute 1", "global flexfield attribute 1"],
    "GLOBAL_ATTRIBUTE2": ["global attribute 2", "global flexfield attribute 2"],
    "GLOBAL_ATTRIBUTE3": ["global attribute 3", "global flexfield attribute 3"],
    "GLOBAL_ATTRIBUTE4": ["global attribute 4", "global flexfield attribute 4"],
    "GLOBAL_ATTRIBUTE5": ["global attribute 5", "global flexfield attribute 5"],
    "GLOBAL_ATTRIBUTE6": ["global attribute 6", "global flexfield attribute 6"],
    "GLOBAL_ATTRIBUTE7": ["global attribute 7", "global flexfield attribute 7"],
    "GLOBAL_ATTRIBUTE8": ["global attribute 8", "global flexfield attribute 8"],
    "GLOBAL_ATTRIBUTE9": ["global attribute 9", "global flexfield attribute 9"],
    "GLOBAL_ATTRIBUTE10": ["global attribute 10", "global flexfield attribute 10"],
    "GLOBAL_ATTRIBUTE11": ["global attribute 11", "global flexfield attribute 11"],
    "GLOBAL_ATTRIBUTE12": ["global attribute 12", "global flexfield attribute 12"],
    "GLOBAL_ATTRIBUTE13": ["global attribute 13", "global flexfield attribute 13"],
    "GLOBAL_ATTRIBUTE14": ["global attribute 14", "global flexfield attribute 14"],
    "GLOBAL_ATTRIBUTE15": ["global attribute 15", "global flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE16": ["global attribute 16", "global flexfield attribute 16"],
    "GLOBAL_ATTRIBUTE17": ["global attribute 17", "global flexfield attribute 17"],
    "GLOBAL_ATTRIBUTE18": ["global attribute 18", "global flexfield attribute 18"],
    "GLOBAL_ATTRIBUTE19": ["global attribute 19", "global flexfield attribute 19"],
    "GLOBAL_ATTRIBUTE20": ["global attribute 20", "global flexfield attribute 20"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "LAST_UPDATED_BY": ["last updated by", "modifier"],
    "LAST_UPDATE_LOGIN": ["last update login", "login"],
    "CREATED_BY": ["created by", "creator"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "ENTERED_BY": ["entered by", "entry person"],
    "TP_HEADER_ID": ["tp header id", "third party header id"],
    "ECE_TP_LOCATION_CODE": ["ece tp location code", "ece third party location code"],
    "OBJECT_VERSION_NUMBER": ["object version number", "version number"],
    "GEOMETRY": ["geometry", "spatial data"],
    "LOC_INFORMATION18": ["loc information 18", "location info 18"],
    "LOC_INFORMATION19": ["loc information 19", "location info 19"],
    "LOC_INFORMATION20": ["loc information 20", "location info 20"],
    "DERIVED_LOCALE": ["derived locale", "locale"],
    "LEGAL_ADDRESS_FLAG": ["legal address flag", "legal address"],
    "TIMEZONE_CODE": ["timezone code", "timezone"],
    
    # HR_ORGANIZATION_INFORMATION table columns
    "ORG_INFORMATION_ID": ["org information id", "organization information id", "org info id"],
    "ORG_INFORMATION_CONTEXT": ["org information context", "organization information context", "org info context"],
    "ORGANIZATION_ID": ["organization id", "org id", "organization identifier"],
    "ORG_INFORMATION1": ["org information 1", "organization info 1"],
    "ORG_INFORMATION10": ["org information 10", "organization info 10"],
    "ORG_INFORMATION11": ["org information 11", "organization info 11"],
    "ORG_INFORMATION12": ["org information 12", "organization info 12"],
    "ORG_INFORMATION13": ["org information 13", "organization info 13"],
    "ORG_INFORMATION14": ["org information 14", "organization info 14"],
    "ORG_INFORMATION15": ["org information 15", "organization info 15"],
    "ORG_INFORMATION16": ["org information 16", "organization info 16"],
    "ORG_INFORMATION17": ["org information 17", "organization info 17"],
    "ORG_INFORMATION18": ["org information 18", "organization info 18"],
    "ORG_INFORMATION19": ["org information 19", "organization info 19"],
    "ORG_INFORMATION2": ["org information 2", "organization info 2"],
    "ORG_INFORMATION20": ["org information 20", "organization info 20"],
    "ORG_INFORMATION3": ["org information 3", "organization info 3"],
    "ORG_INFORMATION4": ["org information 4", "organization info 4"],
    "ORG_INFORMATION5": ["org information 5", "organization info 5"],
    "ORG_INFORMATION6": ["org information 6", "organization info 6"],
    "ORG_INFORMATION7": ["org information 7", "organization info 7"],
    "ORG_INFORMATION8": ["org information 8", "organization info 8"],
    "ORG_INFORMATION9": ["org information 9", "organization info 9"],
    "REQUEST_ID": ["request id", "request identifier"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id"],
    "PROGRAM_ID": ["program id", "program identifier"],
    "PROGRAM_UPDATE_DATE": ["program update date", "program update"],
    "ATTRIBUTE_CATEGORY": ["attribute category", "flexfield category"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "ATTRIBUTE16": ["attribute 16", "flexfield attribute 16"],
    "ATTRIBUTE17": ["attribute 17", "flexfield attribute 17"],
    "ATTRIBUTE18": ["attribute 18", "flexfield attribute 18"],
    "ATTRIBUTE19": ["attribute 19", "flexfield attribute 19"],
    "ATTRIBUTE20": ["attribute 20", "flexfield attribute 20"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "LAST_UPDATED_BY": ["last updated by", "modifier"],
    "LAST_UPDATE_LOGIN": ["last update login", "login"],
    "CREATED_BY": ["created by", "creator"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "OBJECT_VERSION_NUMBER": ["object version number", "version number"],
    "PARTY_ID": ["party id", "party identifier"],
    
    # HZ_PARTIES table columns
    "PARTY_ID": ["party id", "party identifier", "customer id", "supplier id"],
    "PARTY_NUMBER": ["party number", "party no", "customer number", "supplier number"],
    "PARTY_NAME": ["party name", "party", "customer name", "supplier name", "business name"],
    "PARTY_TYPE": ["party type", "customer type", "supplier type", "business type"],
    "VALIDATED_FLAG": ["validated flag", "validation flag", "validated status"],
    "LAST_UPDATED_BY": ["last updated by", "modifier", "updated by"],
    "CREATION_DATE": ["creation date", "created date", "create date", "created on"],
    "LAST_UPDATE_LOGIN": ["last update login", "login", "update login"],
    "REQUEST_ID": ["request id", "request identifier"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id"],
    "CREATED_BY": ["created by", "creator"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date", "updated on"],
    "PROGRAM_ID": ["program id", "program identifier"],
    "PROGRAM_UPDATE_DATE": ["program update date", "program update"],
    "WH_UPDATE_DATE": ["wh update date", "warehouse update date"],
    "ATTRIBUTE_CATEGORY": ["attribute category", "flexfield category"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "ATTRIBUTE16": ["attribute 16", "flexfield attribute 16"],
    "ATTRIBUTE17": ["attribute 17", "flexfield attribute 17"],
    "ATTRIBUTE18": ["attribute 18", "flexfield attribute 18"],
    "ATTRIBUTE19": ["attribute 19", "flexfield attribute 19"],
    "ATTRIBUTE20": ["attribute 20", "flexfield attribute 20"],
    "ATTRIBUTE21": ["attribute 21", "flexfield attribute 21"],
    "ATTRIBUTE22": ["attribute 22", "flexfield attribute 22"],
    "ATTRIBUTE23": ["attribute 23", "flexfield attribute 23"],
    "ATTRIBUTE24": ["attribute 24", "flexfield attribute 24"],
    "GLOBAL_ATTRIBUTE_CATEGORY": ["global attribute category", "global flexfield category"],
    "GLOBAL_ATTRIBUTE1": ["global attribute 1", "global flexfield attribute 1"],
    "GLOBAL_ATTRIBUTE2": ["global attribute 2", "global flexfield attribute 2"],
    "GLOBAL_ATTRIBUTE3": ["global attribute 3", "global flexfield attribute 3"],
    "GLOBAL_ATTRIBUTE4": ["global attribute 4", "global flexfield attribute 4"],
    "GLOBAL_ATTRIBUTE5": ["global attribute 5", "global flexfield attribute 5"],
    "GLOBAL_ATTRIBUTE6": ["global attribute 6", "global flexfield attribute 6"],
    "GLOBAL_ATTRIBUTE7": ["global attribute 7", "global flexfield attribute 7"],
    "GLOBAL_ATTRIBUTE8": ["global attribute 8", "global flexfield attribute 8"],
    "GLOBAL_ATTRIBUTE9": ["global attribute 9", "global flexfield attribute 9"],
    "GLOBAL_ATTRIBUTE10": ["global attribute 10", "global flexfield attribute 10"],
    "GLOBAL_ATTRIBUTE11": ["global attribute 11", "global flexfield attribute 11"],
    "GLOBAL_ATTRIBUTE12": ["global attribute 12", "global flexfield attribute 12"],
    "GLOBAL_ATTRIBUTE13": ["global attribute 13", "global flexfield attribute 13"],
    "GLOBAL_ATTRIBUTE14": ["global attribute 14", "global flexfield attribute 14"],
    "GLOBAL_ATTRIBUTE15": ["global attribute 15", "global flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE16": ["global attribute 16", "global flexfield attribute 16"],
    "GLOBAL_ATTRIBUTE17": ["global attribute 17", "global flexfield attribute 17"],
    "GLOBAL_ATTRIBUTE18": ["global attribute 18", "global flexfield attribute 18"],
    "GLOBAL_ATTRIBUTE19": ["global attribute 19", "global flexfield attribute 19"],
    "GLOBAL_ATTRIBUTE20": ["global attribute 20", "global flexfield attribute 20"],
    "ORIG_SYSTEM_REFERENCE": ["orig system reference", "original system reference", "source system reference"],
    "SIC_CODE": ["sic code", "standard industrial classification code", "industry code"],
    "HQ_BRANCH_IND": ["hq branch ind", "headquarters branch indicator", "hq indicator"],
    "CUSTOMER_KEY": ["customer key", "customer identifier"],
    "TAX_REFERENCE": ["tax reference", "tax id", "tax identification"],
    "JGZZ_FISCAL_CODE": ["jgzz fiscal code", "fiscal code"],
    "DUNS_NUMBER": ["duns number", "duns", "business identification number"],
    "TAX_NAME": ["tax name", "tax code"],
    "PERSON_PRE_NAME_ADJUNCT": ["person pre name adjunct", "name prefix", "title prefix"],
    "PERSON_FIRST_NAME": ["person first name", "first name", "given name"],
    "PERSON_MIDDLE_NAME": ["person middle name", "middle name"],
    "PERSON_LAST_NAME": ["person last name", "last name", "surname", "family name"],
    "PERSON_NAME_SUFFIX": ["person name suffix", "name suffix"],
    "PERSON_TITLE": ["person title", "title"],
    "PERSON_ACADEMIC_TITLE": ["person academic title", "academic title", "degree"],
    "PERSON_PREVIOUS_LAST_NAME": ["person previous last name", "previous last name", "maiden name"],
    "KNOWN_AS": ["known as", "also known as", "alias"],
    "PERSON_IDEN_TYPE": ["person iden type", "person identification type"],
    "PERSON_IDENTIFIER": ["person identifier", "person id"],
    "GROUP_TYPE": ["group type", "organization type"],
    "COUNTRY": ["country", "nation"],
    "ADDRESS1": ["address 1", "address line 1", "street address"],
    "ADDRESS2": ["address 2", "address line 2"],
    "ADDRESS3": ["address 3", "address line 3"],
    "ADDRESS4": ["address 4", "address line 4"],
    "CITY": ["city", "town"],
    "POSTAL_CODE": ["postal code", "zip code", "postcode"],
    "STATE": ["state", "province"],
    "PROVINCE": ["province", "state"],
    "STATUS": ["status", "party status"],
    "COUNTY": ["county"],
    "SIC_CODE_TYPE": ["sic code type", "sic type"],
    "TOTAL_NUM_OF_ORDERS": ["total num of orders", "total orders", "order count"],
    "TOTAL_ORDERED_AMOUNT": ["total ordered amount", "total order amount", "order value"],
    "LAST_ORDERED_DATE": ["last ordered date", "last order date", "recent order date"],
    "URL": ["url", "website", "web address"],
    "EMAIL_ADDRESS": ["email address", "email", "contact email"],
    "DO_NOT_MAIL_FLAG": ["do not mail flag", "do not mail", "mail preference"],
    "ANALYSIS_FY": ["analysis fy", "analysis fiscal year"],
    "FISCAL_YEAREND_MONTH": ["fiscal yearend month", "fiscal year end month"],
    "EMPLOYEES_TOTAL": ["employees total", "total employees", "employee count"],
    "CURR_FY_POTENTIAL_REVENUE": ["curr fy potential revenue", "current fiscal year potential revenue"],
    "NEXT_FY_POTENTIAL_REVENUE": ["next fy potential revenue", "next fiscal year potential revenue"],
    "YEAR_ESTABLISHED": ["year established", "established year", "founded year"],
    "GSA_INDICATOR_FLAG": ["gsa indicator flag", "gsa flag", "government service administration flag"],
    "MISSION_STATEMENT": ["mission statement", "company mission"],
    "ORGANIZATION_NAME_PHONETIC": ["organization name phonetic", "phonetic org name"],
    "PERSON_FIRST_NAME_PHONETIC": ["person first name phonetic", "phonetic first name"],
    "PERSON_LAST_NAME_PHONETIC": ["person last name phonetic", "phonetic last name"],
    "LANGUAGE_NAME": ["language name", "language"],
    "CATEGORY_CODE": ["category code", "category"],
    "REFERENCE_USE_FLAG": ["reference use flag", "reference flag"],
    "THIRD_PARTY_FLAG": ["third party flag", "third party"],
    "COMPETITOR_FLAG": ["competitor flag", "competitor"],
    "SALUTATION": ["salutation", "greeting"],
    "KNOWN_AS2": ["known as 2", "alias 2"],
    "KNOWN_AS3": ["known as 3", "alias 3"],
    "KNOWN_AS4": ["known as 4", "alias 4"],
    "KNOWN_AS5": ["known as 5", "alias 5"],
    "DUNS_NUMBER_C": ["duns number c", "duns c"],
    "OBJECT_VERSION_NUMBER": ["object version number", "version number"],
    "CREATED_BY_MODULE": ["created by module", "module"],
    "APPLICATION_ID": ["application id", "app id"],
    "PRIMARY_PHONE_CONTACT_PT_ID": ["primary phone contact pt id", "primary phone contact point id"],
    "PRIMARY_PHONE_PURPOSE": ["primary phone purpose", "phone purpose"],
    "PRIMARY_PHONE_LINE_TYPE": ["primary phone line type", "phone line type"],
    "PRIMARY_PHONE_COUNTRY_CODE": ["primary phone country code", "phone country code"],
    "PRIMARY_PHONE_AREA_CODE": ["primary phone area code", "phone area code"],
    "PRIMARY_PHONE_NUMBER": ["primary phone number", "phone number", "contact number"],
    "PRIMARY_PHONE_EXTENSION": ["primary phone extension", "phone extension"],
    "CERTIFICATION_LEVEL": ["certification level", "certification"],
    "CERT_REASON_CODE": ["cert reason code", "certification reason code"],
    "PREFERRED_CONTACT_METHOD": ["preferred contact method", "contact method", "preferred contact"],
    "HOME_COUNTRY": ["home country", "residence country"],
    "PERSON_BO_VERSION": ["person bo version", "person business object version"],
    "ORG_BO_VERSION": ["org bo version", "organization business object version"],
    "PERSON_CUST_BO_VERSION": ["person cust bo version", "person customer business object version"],
    "ORG_CUST_BO_VERSION": ["org cust bo version", "organization customer business object version"],
    
    # HZ_CUST_ACCOUNTS table columns
    "CUST_ACCOUNT_ID": ["cust account id", "customer account id", "account id"],
    "PARTY_ID": ["party id", "party identifier"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "ACCOUNT_NUMBER": ["account number", "account no", "customer account number"],
    "LAST_UPDATED_BY": ["last updated by", "modifier"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "CREATED_BY": ["created by", "creator"],
    "LAST_UPDATE_LOGIN": ["last update login", "login"],
    "REQUEST_ID": ["request id", "request identifier"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id"],
    "PROGRAM_ID": ["program id", "program identifier"],
    "PROGRAM_UPDATE_DATE": ["program update date", "program update"],
    "WH_UPDATE_DATE": ["wh update date", "warehouse update date"],
    "ATTRIBUTE_CATEGORY": ["attribute category", "flexfield category"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "ATTRIBUTE16": ["attribute 16", "flexfield attribute 16"],
    "ATTRIBUTE17": ["attribute 17", "flexfield attribute 17"],
    "ATTRIBUTE18": ["attribute 18", "flexfield attribute 18"],
    "ATTRIBUTE19": ["attribute 19", "flexfield attribute 19"],
    "ATTRIBUTE20": ["attribute 20", "flexfield attribute 20"],
    "GLOBAL_ATTRIBUTE_CATEGORY": ["global attribute category", "global flexfield category"],
    "GROUP_ATTRIBUTE1": ["group attribute 1", "group flexfield attribute 1"],
    "GROUP_ATTRIBUTE2": ["group attribute 2", "group flexfield attribute 2"],
    "GROUP_ATTRIBUTE3": ["group attribute 3", "group flexfield attribute 3"],
    "GROUP_ATTRIBUTE4": ["group attribute 4", "group flexfield attribute 4"],
    "GROUP_ATTRIBUTE5": ["group attribute 5", "group flexfield attribute 5"],
    "GROUP_ATTRIBUTE6": ["group attribute 6", "group flexfield attribute 6"],
    "GROUP_ATTRIBUTE7": ["group attribute 7", "group flexfield attribute 7"],
    "GROUP_ATTRIBUTE8": ["group attribute 8", "group flexfield attribute 8"],
    "GROUP_ATTRIBUTE9": ["group attribute 9", "group flexfield attribute 9"],
    "GROUP_ATTRIBUTE10": ["group attribute 10", "group flexfield attribute 10"],
    "GROUP_ATTRIBUTE11": ["group attribute 11", "group flexfield attribute 11"],
    "GROUP_ATTRIBUTE12": ["group attribute 12", "group flexfield attribute 12"],
    "GROUP_ATTRIBUTE13": ["group attribute 13", "group flexfield attribute 13"],
    "GROUP_ATTRIBUTE14": ["group attribute 14", "group flexfield attribute 14"],
    "GROUP_ATTRIBUTE15": ["group attribute 15", "group flexfield attribute 15"],
    
    # WSH_DELIVERY_DETAILS table columns
    "DELIVERY_DETAIL_ID": ["delivery detail id", "delivery detail identifier", "shipment detail id", "shipment detail identifier"],
    "SOURCE_CODE": ["source code", "origin code", "document source code"],
    "SOURCE_HEADER_ID": ["source header id", "source header identifier", "document header id"],
    "SOURCE_LINE_ID": ["source line id", "source line identifier", "document line id"],
    "SOURCE_HEADER_TYPE_ID": ["source header type id", "source header type identifier", "document header type id"],
    "SOURCE_HEADER_TYPE_NAME": ["source header type name", "source header type", "document header type name"],
    "CUST_PO_NUMBER": ["customer po number", "customer purchase order number", "cust po", "customer po"],
    "CUSTOMER_ID": ["customer id", "customer identifier", "client id"],
    "SOLD_TO_CONTACT_ID": ["sold to contact id", "sold to contact identifier", "customer contact id"],
    "INVENTORY_ITEM_ID": ["inventory item id", "item id", "inventory id", "item identifier"],
    "ITEM_DESCRIPTION": ["item description", "product description", "item desc"],
    "SHIP_SET_ID": ["ship set id", "ship set identifier", "shipment set id"],
    "ARRIVAL_SET_ID": ["arrival set id", "arrival set identifier", "receipt set id"],
    "TOP_MODEL_LINE_ID": ["top model line id", "top model line identifier", "configuration model id"],
    "ATO_LINE_ID": ["ato line id", "ato line identifier", "assemble to order line id"],
    "HOLD_CODE": ["hold code", "delivery hold code", "shipment hold code"],
    "SHIP_MODEL_COMPLETE_FLAG": ["ship model complete flag", "model shipment complete", "configuration complete flag"],
    "HAZARD_CLASS_ID": ["hazard class id", "hazard class identifier", "dangerous goods class id"],
    "COUNTRY_OF_ORIGIN": ["country of origin", "origin country", "made in country"],
    "CLASSIFICATION": ["classification", "item classification", "product classification"],
    "SHIP_FROM_LOCATION_ID": ["ship from location id", "ship from location identifier", "origin location id"],
    "ORGANIZATION_ID": ["organization id", "org id", "organization identifier", "inventory org id"],
    "SHIP_TO_LOCATION_ID": ["ship to location id", "ship to location identifier", "destination location id"],
    "SHIP_TO_CONTACT_ID": ["ship to contact id", "ship to contact identifier", "delivery contact id"],
    "DELIVER_TO_LOCATION_ID": ["deliver to location id", "deliver to location identifier", "final destination id"],
    "DELIVER_TO_CONTACT_ID": ["deliver to contact id", "deliver to contact identifier", "final contact id"],
    "INTMED_SHIP_TO_LOCATION_ID": ["intermediate ship to location id", "intermediate ship to location identifier", "intmed ship to location id"],
    "INTMED_SHIP_TO_CONTACT_ID": ["intermediate ship to contact id", "intermediate ship to contact identifier", "intmed ship to contact id"],
    "SHIP_TOLERANCE_ABOVE": ["ship tolerance above", "over shipment tolerance", "tolerance above"],
    "SHIP_TOLERANCE_BELOW": ["ship tolerance below", "under shipment tolerance", "tolerance below"],
    "SRC_REQUESTED_QUANTITY": ["source requested quantity", "original requested quantity", "src req qty"],
    "SRC_REQUESTED_QUANTITY_UOM": ["source requested quantity uom", "source requested quantity unit of measure", "src req qty uom"],
    "CANCELLED_QUANTITY": ["cancelled quantity", "canceled quantity", "cancelled qty"],
    "REQUESTED_QUANTITY": ["requested quantity", "req quantity", "ordered quantity"],
    "REQUESTED_QUANTITY_UOM": ["requested quantity uom", "requested quantity unit of measure", "req qty uom"],
    "SHIPPED_QUANTITY": ["shipped quantity", "shipped qty", "delivered quantity"],
    "DELIVERED_QUANTITY": ["delivered quantity", "delivered qty", "received quantity"],
    "QUALITY_CONTROL_QUANTITY": ["quality control quantity", "qc quantity", "inspection quantity"],
    "CYCLE_COUNT_QUANTITY": ["cycle count quantity", "cycle count qty", "inventory count quantity"],
    "MOVE_ORDER_LINE_ID": ["move order line id", "move order line identifier", "inventory move id"],
    "SUBINVENTORY": ["subinventory", "subinv", "storage subinventory"],
    "REVISION": ["revision", "item revision", "product revision"],
    "LOT_NUMBER": ["lot number", "lot", "batch number", "batch"],
    "RELEASED_STATUS": ["released status", "release status", "delivery status"],
    "CUSTOMER_REQUESTED_LOT_FLAG": ["customer requested lot flag", "customer lot flag", "specific lot requested"],
    "SERIAL_NUMBER": ["serial number", "serial", "item serial"],
    "LOCATOR_ID": ["locator id", "locator identifier", "storage locator id"],
    "DATE_REQUESTED": ["date requested", "requested date", "delivery requested date"],
    "DATE_SCHEDULED": ["date scheduled", "scheduled date", "planned delivery date"],
    "MASTER_CONTAINER_ITEM_ID": ["master container item id", "master container item identifier", "container item id"],
    "DETAIL_CONTAINER_ITEM_ID": ["detail container item id", "detail container item identifier", "container detail id"],
    "LOAD_SEQ_NUMBER": ["load sequence number", "load seq number", "loading sequence"],
    "SHIP_METHOD_CODE": ["ship method code", "shipping method code", "delivery method code"],
    "CARRIER_ID": ["carrier id", "carrier identifier", "shipping carrier id"],
    "FREIGHT_TERMS_CODE": ["freight terms code", "freight terms", "shipping terms code"],
    "SHIPMENT_PRIORITY_CODE": ["shipment priority code", "delivery priority code", "shipping priority"],
    "FOB_CODE": ["fob code", "freight on board code", "fob terms"],
    "CUSTOMER_ITEM_ID": ["customer item id", "customer item identifier", "customer product id"],
    "DEP_PLAN_REQUIRED_FLAG": ["dependent plan required flag", "dep plan required flag", "planning dependency flag"],
    "CUSTOMER_PROD_SEQ": ["customer production sequence", "customer prod seq", "customer manufacturing sequence"],
    "CUSTOMER_DOCK_CODE": ["customer dock code", "customer dock", "delivery dock code"],
    "NET_WEIGHT": ["net weight", "item net weight", "product net weight"],
    "WEIGHT_UOM_CODE": ["weight uom code", "weight unit of measure code", "weight measurement unit"],
    "VOLUME": ["volume", "item volume", "product volume"],
    "VOLUME_UOM_CODE": ["volume uom code", "volume unit of measure code", "volume measurement unit"],
    "SHIPPING_INSTRUCTIONS": ["shipping instructions", "delivery instructions", "shipment instructions"],
    "PACKING_INSTRUCTIONS": ["packing instructions", "packaging instructions", "packing notes"],
    "PROJECT_ID": ["project id", "project identifier", "project number"],
    "TASK_ID": ["task id", "task identifier", "task number"],
    "ORG_ID": ["org id", "organization id", "operating unit id"],
    "OE_INTERFACED_FLAG": ["oe interfaced flag", "order entry interfaced flag", "sales order interfaced"],
    "MVT_STAT_STATUS": ["movement status", "mvt stat status", "inventory movement status"],
    "TRACKING_NUMBER": ["tracking number", "shipment tracking number", "delivery tracking"],
    "TRANSACTION_TEMP_ID": ["transaction temp id", "transaction temporary id", "temp transaction id"],
    "TP_ATTRIBUTE_CATEGORY": ["third party attribute category", "tp attribute category", "third party flexfield category"],
    "TP_ATTRIBUTE1": ["third party attribute 1", "tp attribute 1", "third party flexfield attribute 1"],
    "TP_ATTRIBUTE2": ["third party attribute 2", "tp attribute 2", "third party flexfield attribute 2"],
    "TP_ATTRIBUTE3": ["third party attribute 3", "tp attribute 3", "third party flexfield attribute 3"],
    "TP_ATTRIBUTE4": ["third party attribute 4", "tp attribute 4", "third party flexfield attribute 4"],
    "TP_ATTRIBUTE5": ["third party attribute 5", "tp attribute 5", "third party flexfield attribute 5"],
    "TP_ATTRIBUTE6": ["third party attribute 6", "tp attribute 6", "third party flexfield attribute 6"],
    "TP_ATTRIBUTE7": ["third party attribute 7", "tp attribute 7", "third party flexfield attribute 7"],
    "TP_ATTRIBUTE8": ["third party attribute 8", "tp attribute 8", "third party flexfield attribute 8"],
    "TP_ATTRIBUTE9": ["third party attribute 9", "tp attribute 9", "third party flexfield attribute 9"],
    "TP_ATTRIBUTE10": ["third party attribute 10", "tp attribute 10", "third party flexfield attribute 10"],
    "TP_ATTRIBUTE11": ["third party attribute 11", "tp attribute 11", "third party flexfield attribute 11"],
    "TP_ATTRIBUTE12": ["third party attribute 12", "tp attribute 12", "third party flexfield attribute 12"],
    "TP_ATTRIBUTE13": ["third party attribute 13", "tp attribute 13", "third party flexfield attribute 13"],
    "TP_ATTRIBUTE14": ["third party attribute 14", "tp attribute 14", "third party flexfield attribute 14"],
    "TP_ATTRIBUTE15": ["third party attribute 15", "tp attribute 15", "third party flexfield attribute 15"],
    "ATTRIBUTE_CATEGORY": ["attribute category", "flexfield category"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "CREATED_BY": ["created by", "creator", "created by user"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "LAST_UPDATED_BY": ["last updated by", "modifier", "updated by"],
    "LAST_UPDATE_LOGIN": ["last update login", "login", "update login"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id", "concurrent program application id"],
    "PROGRAM_ID": ["program id", "concurrent program id", "program identifier"],
    "PROGRAM_UPDATE_DATE": ["program update date", "concurrent program update date", "program modification date"],
    "REQUEST_ID": ["request id", "concurrent request id", "request identifier"],
    "MOVEMENT_ID": ["movement id", "movement identifier", "inventory movement id"],
    "SPLIT_FROM_DELIVERY_DETAIL_ID": ["split from delivery detail id", "split from delivery detail identifier", "delivery detail split from"],
    "INV_INTERFACED_FLAG": ["inventory interfaced flag", "inv interfaced flag", "inventory interface flag"],
    "SEAL_CODE": ["seal code", "container seal code", "shipment seal"],
    "MINIMUM_FILL_PERCENT": ["minimum fill percent", "minimum fill percentage", "min fill percent"],
    "MAXIMUM_VOLUME": ["maximum volume", "max volume", "volume limit"],
    "MAXIMUM_LOAD_WEIGHT": ["maximum load weight", "max load weight", "weight limit"],
    "MASTER_SERIAL_NUMBER": ["master serial number", "master serial", "container serial number"],
    "GROSS_WEIGHT": ["gross weight", "total weight", "shipment weight"],
    "FILL_PERCENT": ["fill percent", "fill percentage", "container fill percent"],
    "CONTAINER_NAME": ["container name", "shipping container name", "box name"],
    "CONTAINER_TYPE_CODE": ["container type code", "container type", "box type code"],
    "CONTAINER_FLAG": ["container flag", "containerized flag", "is containerized"],
    "PREFERRED_GRADE": ["preferred grade", "preferred quality grade", "item grade"],
    "SRC_REQUESTED_QUANTITY2": ["source requested quantity 2", "source requested quantity second", "src req qty 2"],
    "SRC_REQUESTED_QUANTITY_UOM2": ["source requested quantity uom 2", "source requested quantity unit of measure 2", "src req qty uom 2"],
    "REQUESTED_QUANTITY2": ["requested quantity 2", "requested quantity second", "req qty 2"],
    "SHIPPED_QUANTITY2": ["shipped quantity 2", "shipped quantity second", "shipped qty 2"],
    "DELIVERED_QUANTITY2": ["delivered quantity 2", "delivered quantity second", "delivered qty 2"],
    "CANCELLED_QUANTITY2": ["cancelled quantity 2", "cancelled quantity second", "cancelled qty 2"],
    "QUALITY_CONTROL_QUANTITY2": ["quality control quantity 2", "qc quantity 2", "inspection quantity 2"],
    "CYCLE_COUNT_QUANTITY2": ["cycle count quantity 2", "cycle count qty 2", "inventory count quantity 2"],
    "REQUESTED_QUANTITY_UOM2": ["requested quantity uom 2", "requested quantity unit of measure 2", "req qty uom 2"],
    "SUBLOT_NUMBER": ["sublot number", "sublot", "partial lot number"],
    "UNIT_PRICE": ["unit price", "price per unit", "item unit price"],
    "CURRENCY_CODE": ["currency code", "currency", "monetary currency"],
    "UNIT_NUMBER": ["unit number", "item unit number", "unit id"],
    "FREIGHT_CLASS_CAT_ID": ["freight class category id", "freight class cat id", "shipping class id"],
    "COMMODITY_CODE_CAT_ID": ["commodity code category id", "commodity code cat id", "product category id"],
    "LPN_CONTENT_ID": ["lpn content id", "license plate number content id", "lpn contents id"],
    "SHIP_TO_SITE_USE_ID": ["ship to site use id", "ship to site use identifier", "delivery site use id"],
    "DELIVER_TO_SITE_USE_ID": ["deliver to site use id", "deliver to site use identifier", "final site use id"],
    "LPN_ID": ["lpn id", "license plate number id", "shipping container id"],
    "INSPECTION_FLAG": ["inspection flag", "quality inspection flag", "qc flag"],
    "ORIGINAL_SUBINVENTORY": ["original subinventory", "original subinv", "source subinventory"],
    "SOURCE_HEADER_NUMBER": ["source header number", "source header", "document header number"],
    "SOURCE_LINE_NUMBER": ["source line number", "source line", "document line number"],
    "PICKABLE_FLAG": ["pickable flag", "is pickable", "can be picked"],
    "CUSTOMER_PRODUCTION_LINE": ["customer production line", "customer production", "customer manufacturing line"],
    "CUSTOMER_JOB": ["customer job", "customer work order", "client job"],
    "CUST_MODEL_SERIAL_NUMBER": ["customer model serial number", "customer model serial", "client model serial"],
    "TO_SERIAL_NUMBER": ["to serial number", "end serial number", "serial range end"],
    "PICKED_QUANTITY": ["picked quantity", "picked qty", "items picked"],
    "PICKED_QUANTITY2": ["picked quantity 2", "picked quantity second", "picked qty 2"],
    "RECEIVED_QUANTITY": ["received quantity", "received qty", "qty received"],
    "RECEIVED_QUANTITY2": ["received quantity 2", "received quantity second", "received qty 2"],
    "SOURCE_LINE_SET_ID": ["source line set id", "source line set identifier", "document line set id"],
    "BATCH_ID": ["batch id", "batch identifier", "processing batch id"],
    "TRANSACTION_ID": ["transaction id", "transaction identifier", "inventory transaction id"],
    "SERVICE_LEVEL": ["service level", "delivery service level", "shipping service level"],
    "MODE_OF_TRANSPORT": ["mode of transport", "transport mode", "shipping method"],
    "EARLIEST_PICKUP_DATE": ["earliest pickup date", "earliest pickup", "first pickup date"],
    "LATEST_PICKUP_DATE": ["latest pickup date", "latest pickup", "last pickup date"],
    "EARLIEST_DROPOFF_DATE": ["earliest dropoff date", "earliest dropoff", "first dropoff date"],
    "LATEST_DROPOFF_DATE": ["latest dropoff date", "latest dropoff", "last dropoff date"],
    "REQUEST_DATE_TYPE_CODE": ["request date type code", "request date type", "delivery date type"],
    "TP_DELIVERY_DETAIL_ID": ["third party delivery detail id", "tp delivery detail id", "third party shipment detail"],
    "SOURCE_DOCUMENT_TYPE_ID": ["source document type id", "source document type identifier", "document type id"],
    "VENDOR_ID": ["vendor id", "vendor identifier", "supplier id"],
    "SHIP_FROM_SITE_ID": ["ship from site id", "ship from site identifier", "origin site id"],
    "IGNORE_FOR_PLANNING": ["ignore for planning", "ignore planning", "exclude from planning"],
    "LINE_DIRECTION": ["line direction", "delivery direction", "shipment direction"],
    "PARTY_ID": ["party id", "party identifier", "business partner id"],
    "ROUTING_REQ_ID": ["routing request id", "routing req id", "delivery routing id"],
    "SHIPPING_CONTROL": ["shipping control", "delivery control", "shipment control"],
    "SOURCE_BLANKET_REFERENCE_ID": ["source blanket reference id", "source blanket ref id", "blanket order ref id"],
    "SOURCE_BLANKET_REFERENCE_NUM": ["source blanket reference num", "source blanket reference number", "blanket order ref num"],
    "PO_SHIPMENT_LINE_ID": ["po shipment line id", "purchase order shipment line id", "po delivery line id"],
    "PO_SHIPMENT_LINE_NUMBER": ["po shipment line number", "purchase order shipment line number", "po delivery line number"],
    "SCHEDULED_QUANTITY": ["scheduled quantity", "planned quantity", "scheduled qty"],
    "RETURNED_QUANTITY": ["returned quantity", "returned qty", "qty returned"],
    "SCHEDULED_QUANTITY2": ["scheduled quantity 2", "scheduled quantity second", "scheduled qty 2"],
    "RETURNED_QUANTITY2": ["returned quantity 2", "returned quantity second", "returned qty 2"],
    "SOURCE_LINE_TYPE_CODE": ["source line type code", "source line type", "document line type code"],
    "RCV_SHIPMENT_LINE_ID": ["receiving shipment line id", "rcv shipment line id", "receipt shipment line id"],
    "SUPPLIER_ITEM_NUMBER": ["supplier item number", "supplier item", "vendor item number"],
    "FILLED_VOLUME": ["filled volume", "container filled volume", "occupied volume"],
    "UNIT_WEIGHT": ["unit weight", "item unit weight", "weight per unit"],
    "UNIT_VOLUME": ["unit volume", "item unit volume", "volume per unit"],
    "WV_FROZEN_FLAG": ["wv frozen flag", "wv frozen", "weight volume frozen flag"],
    "PO_REVISION_NUMBER": ["po revision number", "purchase order revision number", "po rev number"],
    "RELEASE_REVISION_NUMBER": ["release revision number", "release rev number", "delivery release revision"],
    "REPLENISHMENT_STATUS": ["replenishment status", "replenishment", "inventory replenishment status"],
    "ORIGINAL_LOT_NUMBER": ["original lot number", "original lot", "source lot number"],
    "ORIGINAL_REVISION": ["original revision", "original item revision", "source revision"],
    "ORIGINAL_LOCATOR_ID": ["original locator id", "original locator identifier", "source locator id"],
    "REFERENCE_NUMBER": ["reference number", "ref number", "document reference"],
    "REFERENCE_LINE_NUMBER": ["reference line number", "reference line", "document reference line"],
    "REFERENCE_LINE_QUANTITY": ["reference line quantity", "reference line qty", "document reference quantity"],
    "REFERENCE_LINE_QUANTITY_UOM": ["reference line quantity uom", "reference line quantity unit of measure", "ref line qty uom"],
    "CLIENT_ID": ["client id", "client identifier", "customer id"],
    "SHIPMENT_BATCH_ID": ["shipment batch id", "shipment batch identifier", "delivery batch id"],
    "SHIPMENT_LINE_NUMBER": ["shipment line number", "shipment line", "delivery line number"],
    "REFERENCE_LINE_ID": ["reference line id", "reference line identifier", "document reference line id"],
    "CONSIGNEE_FLAG": ["consignee flag", "consignee", "is consignee"],
    "EQUIPMENT_ID": ["equipment id", "equipment identifier", "shipping equipment id"],
    "MCC_CODE": ["mcc code", "material control code", "inventory control code"],
    "TMS_SUB_BATCH_ID": ["tms sub batch id", "tms sub batch identifier", "transportation sub batch id"],
    "TMS_SUB_BATCH_LINE_NUM": ["tms sub batch line num", "tms sub batch line number", "transportation sub batch line"],
    "TMS_INTERFACE_FLAG": ["tms interface flag", "tms interface", "transportation interface flag"],
    "TMS_SSHIPUNIT_ID": ["tms shipping unit id", "tms sshipunit id", "transportation shipping unit id"],
    "VERIFICATION_STATUS": ["verification status", "verification", "delivery verification status"],
    "REASON_ID": ["reason id", "reason identifier", "reason code"],
    "GROUP_ATTRIBUTE1": ["group attribute 1", "group flexfield attribute 1"],
    "GROUP_ATTRIBUTE2": ["group attribute 2", "group flexfield attribute 2"],
    "GROUP_ATTRIBUTE3": ["group attribute 3", "group flexfield attribute 3"],
    "GROUP_ATTRIBUTE4": ["group attribute 4", "group flexfield attribute 4"],
    "GROUP_ATTRIBUTE5": ["group attribute 5", "group flexfield attribute 5"],
    "GROUP_ATTRIBUTE6": ["group attribute 6", "group flexfield attribute 6"],
    "GROUP_ATTRIBUTE7": ["group attribute 7", "group flexfield attribute 7"],
    "GROUP_ATTRIBUTE8": ["group attribute 8", "group flexfield attribute 8"],
    "GROUP_ATTRIBUTE9": ["group attribute 9", "group flexfield attribute 9"],
    "GROUP_ATTRIBUTE10": ["group attribute 10", "group flexfield attribute 10"],
    "GROUP_ATTRIBUTE11": ["group attribute 11", "group flexfield attribute 11"],
    "GROUP_ATTRIBUTE12": ["group attribute 12", "group flexfield attribute 12"],
    "GROUP_ATTRIBUTE13": ["group attribute 13", "group flexfield attribute 13"],
    "GROUP_ATTRIBUTE14": ["group attribute 14", "group flexfield attribute 14"],
    "GROUP_ATTRIBUTE15": ["group attribute 15", "group flexfield attribute 15"],
    
# =========================
# Core search helpers
    "GLOBAL_ATTRIBUTE1": ["global attribute 1", "global flexfield attribute 1"],
    "GLOBAL_ATTRIBUTE2": ["global attribute 2", "global flexfield attribute 2"],
    "GLOBAL_ATTRIBUTE3": ["global attribute 3", "global flexfield attribute 3"],
    "GLOBAL_ATTRIBUTE4": ["global attribute 4", "global flexfield attribute 4"],
    "GLOBAL_ATTRIBUTE5": ["global attribute 5", "global flexfield attribute 5"],
    "GLOBAL_ATTRIBUTE6": ["global attribute 6", "global flexfield attribute 6"],
    "GLOBAL_ATTRIBUTE7": ["global attribute 7", "global flexfield attribute 7"],
    "GLOBAL_ATTRIBUTE8": ["global attribute 8", "global flexfield attribute 8"],
    "GLOBAL_ATTRIBUTE9": ["global attribute 9", "global flexfield attribute 9"],
    "GLOBAL_ATTRIBUTE10": ["global attribute 10", "global flexfield attribute 10"],
    "GLOBAL_ATTRIBUTE11": ["global attribute 11", "global flexfield attribute 11"],
    "GLOBAL_ATTRIBUTE12": ["global attribute 12", "global flexfield attribute 12"],
    "GLOBAL_ATTRIBUTE13": ["global attribute 13", "global flexfield attribute 13"],
    "GLOBAL_ATTRIBUTE14": ["global attribute 14", "global flexfield attribute 14"],
    "GLOBAL_ATTRIBUTE15": ["global attribute 15", "global flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE16": ["global attribute 16", "global flexfield attribute 16"],
    "GLOBAL_ATTRIBUTE17": ["global attribute 17", "global flexfield attribute 17"],
    "GLOBAL_ATTRIBUTE18": ["global attribute 18", "global flexfield attribute 18"],
    "GLOBAL_ATTRIBUTE19": ["global attribute 19", "global flexfield attribute 19"],
    "GLOBAL_ATTRIBUTE20": ["global attribute 20", "global flexfield attribute 20"],
    "ORIG_SYSTEM_REFERENCE": ["orig system reference", "original system reference"],
    "STATUS": ["status", "account status"],
    "CUSTOMER_TYPE": ["customer type", "cust type"],
    "CUSTOMER_CLASS_CODE": ["customer class code", "cust class code"],
    "PRIMARY_SALESREP_ID": ["primary salesrep id", "primary sales rep id", "sales rep id"],
    "SALES_CHANNEL_CODE": ["sales channel code", "channel code"],
    "ORDER_TYPE_ID": ["order type id", "order type identifier"],
    "PRICE_LIST_ID": ["price list id", "price list identifier"],
    "SUBCATEGORY_CODE": ["subcategory code", "sub category code"],
    "TAX_CODE": ["tax code", "tax"],
    "FOB_POINT": ["fob point", "freight on board point"],
    "FREIGHT_TERM": ["freight term", "freight terms"],
    "SHIP_PARTIAL": ["ship partial", "partial shipment"],
    "SHIP_VIA": ["ship via", "shipping method"],
    "WAREHOUSE_ID": ["warehouse id", "warehouse identifier"],
    "PAYMENT_TERM_ID": ["payment term id", "payment term identifier"],
    "TAX_HEADER_LEVEL_FLAG": ["tax header level flag", "tax header flag"],
    "TAX_ROUNDING_RULE": ["tax rounding rule", "rounding rule"],
    "COTERMINATE_DAY_MONTH": ["coterminate day month", "cotermination date"],
    "PRIMARY_SPECIALIST_ID": ["primary specialist id", "primary specialist"],
    "SECONDARY_SPECIALIST_ID": ["secondary specialist id", "secondary specialist"],
    "ACCOUNT_LIABLE_FLAG": ["account liable flag", "liable flag"],
    "RESTRICTION_LIMIT_AMOUNT": ["restriction limit amount", "limit amount"],
    "CURRENT_BALANCE": ["current balance", "account balance", "balance"],
    "PASSWORD_TEXT": ["password text", "password"],
    "HIGH_PRIORITY_INDICATOR": ["high priority indicator", "priority indicator"],
    "ACCOUNT_ESTABLISHED_DATE": ["account established date", "established date"],
    "ACCOUNT_TERMINATION_DATE": ["account termination date", "termination date"],
    "ACCOUNT_ACTIVATION_DATE": ["account activation date", "activation date"],
    "CREDIT_CLASSIFICATION_CODE": ["credit classification code", "credit class code"],
    "DEPARTMENT": ["department"],
    "MAJOR_ACCOUNT_NUMBER": ["major account number", "major account"],
    "HOTWATCH_SERVICE_FLAG": ["hotwatch service flag", "hotwatch flag"],
    "HOTWATCH_SVC_BAL_IND": ["hotwatch svc bal ind", "hotwatch balance indicator"],
    "HELD_BILL_EXPIRATION_DATE": ["held bill expiration date", "bill expiration date"],
    "HOLD_BILL_FLAG": ["hold bill flag", "bill hold flag"],
    "HIGH_PRIORITY_REMARKS": ["high priority remarks", "priority remarks"],
    "PO_EFFECTIVE_DATE": ["po effective date", "purchase order effective date"],
    "PO_EXPIRATION_DATE": ["po expiration date", "purchase order expiration date"],
    "REALTIME_RATE_FLAG": ["realtime rate flag", "realtime flag"],
    "SINGLE_USER_FLAG": ["single user flag", "single user"],
    "WATCH_ACCOUNT_FLAG": ["watch account flag", "watch flag"],
    "WATCH_BALANCE_INDICATOR": ["watch balance indicator", "balance indicator"],
    "GEO_CODE": ["geo code", "geographical code"],
    "ACCT_LIFE_CYCLE_STATUS": ["acct life cycle status", "account life cycle status"],
    "ACCOUNT_NAME": ["account name", "customer account name"],
    "DEPOSIT_REFUND_METHOD": ["deposit refund method", "refund method"],
    "DORMANT_ACCOUNT_FLAG": ["dormant account flag", "dormant flag"],
    "NPA_NUMBER": ["npa number", "npa"],
    "PIN_NUMBER": ["pin number", "pin"],
    "SUSPENSION_DATE": ["suspension date", "suspend date"],
    "WRITE_OFF_ADJUSTMENT_AMOUNT": ["write off adjustment amount", "adjustment amount"],
    "WRITE_OFF_PAYMENT_AMOUNT": ["write off payment amount", "payment amount"],
    "WRITE_OFF_AMOUNT": ["write off amount", "writeoff amount"],
    "SOURCE_CODE": ["source code", "source"],
    "COMPETITOR_TYPE": ["competitor type", "competitor"],
    "COMMENTS": ["comments", "notes"],
    "DATES_NEGATIVE_TOLERANCE": ["dates negative tolerance", "negative tolerance"],
    "DATES_POSITIVE_TOLERANCE": ["dates positive tolerance", "positive tolerance"],
    "DATE_TYPE_PREFERENCE": ["date type preference", "date preference"],
    "OVER_SHIPMENT_TOLERANCE": ["over shipment tolerance", "over tolerance"],
    "UNDER_SHIPMENT_TOLERANCE": ["under shipment tolerance", "under tolerance"],
    "OVER_RETURN_TOLERANCE": ["over return tolerance", "return over tolerance"],
    "UNDER_RETURN_TOLERANCE": ["under return tolerance", "return under tolerance"],
    "ITEM_CROSS_REF_PREF": ["item cross ref pref", "cross reference preference"],
    "SHIP_SETS_INCLUDE_LINES_FLAG": ["ship sets include lines flag", "ship sets flag"],
    "ARRIVALSETS_INCLUDE_LINES_FLAG": ["arrival sets include lines flag", "arrival sets flag"],
    "SCHED_DATE_PUSH_FLAG": ["sched date push flag", "schedule date push flag"],
    "INVOICE_QUANTITY_RULE": ["invoice quantity rule", "invoice rule"],
    "PRICING_EVENT": ["pricing event", "price event"],
    "ACCOUNT_REPLICATION_KEY": ["account replication key", "replication key"],
    "STATUS_UPDATE_DATE": ["status update date", "status date"],
    "AUTOPAY_FLAG": ["autopay flag", "auto pay flag"],
    "NOTIFY_FLAG": ["notify flag", "notification flag"],
    "LAST_BATCH_ID": ["last batch id", "batch id"],
    "ORG_ID": ["org id", "organization id"],
    "OBJECT_VERSION_NUMBER": ["object version number", "version number"],
    "CREATED_BY_MODULE": ["created by module", "module"],
    "APPLICATION_ID": ["application id", "app id"],
    "SELLING_PARTY_ID": ["selling party id", "selling party"],
    "FEDERAL_ENTITY_TYPE": ["federal entity type", "federal type"],
    "TRADING_PARTNER_AGENCY_ID": ["trading partner agency id", "trading partner id"],
    "DUNS_EXTENSION": ["duns extension", "duns ext"],
    "ADVANCE_PAYMENT_INDICATOR": ["advance payment indicator", "advance payment"],
    "CANCEL_UNSHIPPED_LINES_FLAG": ["cancel unshipped lines flag", "cancel lines flag"],
    
    # HZ_CUST_ACCOUNTS table business terms
    "HZ_CUST_ACCOUNTS": ["customer accounts", "cust accounts", "customer account table", "account information", "customer data", "client accounts"],
    
    # HZ_PARTIES table business terms
    "HZ_PARTIES": ["parties", "party information", "customer data", "supplier data", "business entities", "party master data", "party records"],
    
    # HR_ORGANIZATION_INFORMATION table business terms
    "HR_ORGANIZATION_INFORMATION": ["hr organization information", "organization information", "hr org info", "org information", "organization info"],
    
    # HR_LOCATIONS_ALL table business terms
    "HR_LOCATIONS_ALL": ["hr locations", "locations", "hr location table", "location information", "address information", "contact locations", "geographical locations", "physical locations"],
    
    # EMP_DETAILS_VIEW table business terms
    "EMP_DETAILS_VIEW": ["employee details", "staff information", "employee view", "hr employee data", "worker details", "personnel information"],

    # Employee-related terms
    "EMPLOYEE_ID": ["employee id", "emp id", "worker id", "staff id"],
    "JOB_ID": ["job id", "position id"],
    "MANAGER_ID": ["manager id", "supervisor id"],
    "DEPARTMENT_ID": ["department id", "dept id"],
    "LOCATION_ID": ["location id", "loc id"],
    "COUNTRY_ID": ["country id"],
    "FIRST_NAME": ["first name", "given name"],
    "LAST_NAME": ["last name", "surname", "family name"],
    "SALARY": ["salary", "compensation", "wage"],
    "COMMISSION_PCT": ["commission percentage", "commission pct", "sales commission"],
    "DEPARTMENT_NAME": ["department name", "dept name"],
    "JOB_TITLE": ["job title", "position title"],
    "CITY": ["city"],
    "STATE_PROVINCE": ["state", "province"],
    "COUNTRY_NAME": ["country name"],
    "REGION_NAME": ["region name"],
    
    # Business context terms
    "BUSINESS_GROUP": ["business group", "bg", "business unit group", "business groups"],
    "OPERATING_UNIT": ["operating unit", "ou", "business unit", "org unit", "operating units"],
    "ORGANIZATION": ["organization", "org", "entity", "organizations"],
    "LEGAL_ENTITY": ["legal entity", "le", "corporate entity", "legal context", "legal entities"],
    "SET_OF_BOOKS": ["set of books", "sob", "ledger", "accounting book", "books", "ledger id"],
    "CHART_OF_ACCOUNTS": ["chart of accounts", "coa", "account structure", "chart of account"],
    "INVENTORY_ITEM": ["inventory item", "item", "stock item"],
    "SUBINVENTORY": ["subinventory", "subinv", "secondary inventory"],
    "LOT": ["lot", "batch"],
    "PROJECT": ["project"],
    "TASK": ["task"],
    "COST_GROUP": ["cost group", "default cost group"],
    
    # Status terms
    "ACTIVE": ["active", "currently active", "enabled", "usable", "working", "functional", "available", "current"],
    "INVENTORY_ENABLED": ["inventory enabled", "inventory", "stock enabled", "inventory available", "inventory status"],
    "RESERVABLE": ["reservable", "can be reserved", "reservation allowed", "allow reservations"],
    "AVAILABLE": ["available", "in stock", "on hand"],
    "CONSIGN": ["consign", "consigned", "consigned inventory"],
    "DISABLE": ["disable", "disabled", "deactivate", "deactivated"],
    
    # Time-related terms
    "THIS_MONTH": ["this month", "current month", "month to date"],
    "QUANTITY": ["quantity", "qty", "amount", "count", "quantities"],
    "TOTAL": ["total", "sum", "aggregate", "combined", "overall"],
    
    # Join relationship terms
    "JOIN": ["join", "link", "connect", "combine", "both", "together", "with", "and"],
    "RELATIONSHIP": ["relationship", "connection", "link", "association", "mapping"],
    
    # New table business terms
    "ONHAND_QUANTITY": ["onhand quantity", "on-hand quantity", "inventory quantity", "stock quantity"],
    "ITEMS_RECEIVED": ["items received", "received items", "inventory received"],
    "SUBINVENTORY_DESCRIPTION": ["subinventory description", "subinv description"],
    "CONSIGN_INVENTORY": ["consigned inventory", "consign inventory", "supplier owned inventory"],
    "RESERVATION": ["reservation", "reserve", "reserved"]
}

# OE_ORDER_HEADERS_ALL table columns
COLUMN_SYNONYMS.update({
    "HEADER_ID": ["header id", "order header id", "sales order id", "order id"],
    "ORG_ID": ["org id", "organization id", "operating unit id"],
    "ORDER_TYPE_ID": ["order type id", "order type identifier"],
    "ORDER_NUMBER": ["order number", "sales order number", "order no"],
    "VERSION_NUMBER": ["version number", "order version"],
    "EXPIRATION_DATE": ["expiration date", "order expiration date", "expiry date"],
    "ORDER_SOURCE_ID": ["order source id", "order source identifier"],
    "SOURCE_DOCUMENT_TYPE_ID": ["source document type id", "source document type identifier"],
    "ORIG_SYS_DOCUMENT_REF": ["orig sys document ref", "original system document reference"],
    "SOURCE_DOCUMENT_ID": ["source document id", "source document identifier"],
    "ORDERED_DATE": ["ordered date", "order date", "sales order date"],
    "REQUEST_DATE": ["request date", "requested date"],
    "PRICING_DATE": ["pricing date", "price date"],
    "SHIPMENT_PRIORITY_CODE": ["shipment priority code", "shipping priority code"],
    "DEMAND_CLASS_CODE": ["demand class code", "demand class"],
    "PRICE_LIST_ID": ["price list id", "price list identifier"],
    "TAX_EXEMPT_FLAG": ["tax exempt flag", "tax exemption flag"],
    "TAX_EXEMPT_NUMBER": ["tax exempt number", "tax exemption number"],
    "TAX_EXEMPT_REASON_CODE": ["tax exempt reason code", "tax exemption reason code"],
    "CONVERSION_RATE": ["conversion rate", "currency conversion rate"],
    "CONVERSION_TYPE_CODE": ["conversion type code", "currency conversion type code"],
    "CONVERSION_RATE_DATE": ["conversion rate date", "currency conversion rate date"],
    "PARTIAL_SHIPMENTS_ALLOWED": ["partial shipments allowed", "partial shipping allowed"],
    "SHIP_TOLERANCE_ABOVE": ["ship tolerance above", "shipping tolerance above"],
    "SHIP_TOLERANCE_BELOW": ["ship tolerance below", "shipping tolerance below"],
    "TRANSACTIONAL_CURR_CODE": ["transactional curr code", "transactional currency code"],
    "AGREEMENT_ID": ["agreement id", "agreement identifier"],
    "TAX_POINT_CODE": ["tax point code", "tax point"],
    "CUST_PO_NUMBER": ["cust po number", "customer po number", "customer purchase order number"],
    "INVOICING_RULE_ID": ["invoicing rule id", "invoicing rule identifier"],
    "ACCOUNTING_RULE_ID": ["accounting rule id", "accounting rule identifier"],
    "PAYMENT_TERM_ID": ["payment term id", "payment term identifier"],
    "SHIPPING_METHOD_CODE": ["shipping method code", "shipping method"],
    "FREIGHT_CARRIER_CODE": ["freight carrier code", "freight carrier"],
    "FOB_POINT_CODE": ["fob point code", "fob point", "freight on board point"],
    "FREIGHT_TERMS_CODE": ["freight terms code", "freight terms"],
    "SOLD_FROM_ORG_ID": ["sold from org id", "sold from organization id"],
    "SOLD_TO_ORG_ID": ["sold to org id", "sold to organization id", "customer org id"],
    "SHIP_FROM_ORG_ID": ["ship from org id", "ship from organization id"],
    "SHIP_TO_ORG_ID": ["ship to org id", "ship to organization id", "delivery org id"],
    "INVOICE_TO_ORG_ID": ["invoice to org id", "invoice to organization id"],
    "DELIVER_TO_ORG_ID": ["deliver to org id", "deliver to organization id"],
    "SOLD_TO_CONTACT_ID": ["sold to contact id", "sold to contact identifier"],
    "SHIP_TO_CONTACT_ID": ["ship to contact id", "ship to contact identifier"],
    "INVOICE_TO_CONTACT_ID": ["invoice to contact id", "invoice to contact identifier"],
    "DELIVER_TO_CONTACT_ID": ["deliver to contact id", "deliver to contact identifier"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "CREATED_BY": ["created by", "creator"],
    "LAST_UPDATED_BY": ["last updated by", "modifier"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "LAST_UPDATE_LOGIN": ["last update login", "login"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id"],
    "PROGRAM_ID": ["program id", "program identifier"],
    "PROGRAM_UPDATE_DATE": ["program update date", "program update"],
    "REQUEST_ID": ["request id", "request identifier"],
    "CONTEXT": ["context", "descriptive flexfield context"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE_CATEGORY": ["global attribute category", "global flexfield category"],
    "GLOBAL_ATTRIBUTE1": ["global attribute 1", "global flexfield attribute 1"],
    "GLOBAL_ATTRIBUTE2": ["global attribute 2", "global flexfield attribute 2"],
    "GLOBAL_ATTRIBUTE3": ["global attribute 3", "global flexfield attribute 3"],
    "GLOBAL_ATTRIBUTE4": ["global attribute 4", "global flexfield attribute 4"],
    "GLOBAL_ATTRIBUTE5": ["global attribute 5", "global flexfield attribute 5"],
    "GLOBAL_ATTRIBUTE6": ["global attribute 6", "global flexfield attribute 6"],
    "GLOBAL_ATTRIBUTE7": ["global attribute 7", "global flexfield attribute 7"],
    "GLOBAL_ATTRIBUTE8": ["global attribute 8", "global flexfield attribute 8"],
    "GLOBAL_ATTRIBUTE9": ["global attribute 9", "global flexfield attribute 9"],
    "GLOBAL_ATTRIBUTE10": ["global attribute 10", "global flexfield attribute 10"],
    "GLOBAL_ATTRIBUTE11": ["global attribute 11", "global flexfield attribute 11"],
    "GLOBAL_ATTRIBUTE12": ["global attribute 12", "global flexfield attribute 12"],
    "GLOBAL_ATTRIBUTE13": ["global attribute 13", "global flexfield attribute 13"],
    "GLOBAL_ATTRIBUTE14": ["global attribute 14", "global flexfield attribute 14"],
    "GLOBAL_ATTRIBUTE15": ["global attribute 15", "global flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE16": ["global attribute 16", "global flexfield attribute 16"],
    "GLOBAL_ATTRIBUTE17": ["global attribute 17", "global flexfield attribute 17"],
    "GLOBAL_ATTRIBUTE18": ["global attribute 18", "global flexfield attribute 18"],
    "GLOBAL_ATTRIBUTE19": ["global attribute 19", "global flexfield attribute 19"],
    "GLOBAL_ATTRIBUTE20": ["global attribute 20", "global flexfield attribute 20"],
    "CANCELLED_FLAG": ["cancelled flag", "canceled flag", "cancel status"],
    "OPEN_FLAG": ["open flag", "open status"],
    "BOOKED_FLAG": ["booked flag", "booked status"],
    "SALESREP_ID": ["salesrep id", "sales rep id", "sales representative id"],
    "RETURN_REASON_CODE": ["return reason code", "return reason"],
    "ORDER_DATE_TYPE_CODE": ["order date type code", "order date type"],
    "EARLIEST_SCHEDULE_LIMIT": ["earliest schedule limit", "earliest scheduling limit"],
    "LATEST_SCHEDULE_LIMIT": ["latest schedule limit", "latest scheduling limit"],
    "PAYMENT_TYPE_CODE": ["payment type code", "payment type"],
    "PAYMENT_AMOUNT": ["payment amount", "amount paid"],
    "CHECK_NUMBER": ["check number", "cheque number"],
    "CREDIT_CARD_CODE": ["credit card code", "credit card type"],
    "CREDIT_CARD_HOLDER_NAME": ["credit card holder name", "card holder name"],
    "CREDIT_CARD_NUMBER": ["credit card number", "card number"],
    "CREDIT_CARD_EXPIRATION_DATE": ["credit card expiration date", "card expiration date"],
    "CREDIT_CARD_APPROVAL_CODE": ["credit card approval code", "card approval code"],
    "SALES_CHANNEL_CODE": ["sales channel code", "channel code"],
    "FIRST_ACK_CODE": ["first ack code", "first acknowledgment code"],
    "FIRST_ACK_DATE": ["first ack date", "first acknowledgment date"],
    "LAST_ACK_CODE": ["last ack code", "last acknowledgment code"],
    "LAST_ACK_DATE": ["last ack date", "last acknowledgment date"],
    "ORDER_CATEGORY_CODE": ["order category code", "order category"],
    "CHANGE_SEQUENCE": ["change sequence", "sequence number"],
    "DROP_SHIP_FLAG": ["drop ship flag", "drop shipment flag"],
    "CUSTOMER_PAYMENT_TERM_ID": ["customer payment term id", "customer payment term identifier"],
    "SHIPPING_INSTRUCTIONS": ["shipping instructions", "delivery instructions"],
    "PACKING_INSTRUCTIONS": ["packing instructions", "packaging instructions"],
    "TP_CONTEXT": ["tp context", "third party context"],
    "TP_ATTRIBUTE1": ["tp attribute 1", "third party attribute 1"],
    "TP_ATTRIBUTE2": ["tp attribute 2", "third party attribute 2"],
    "TP_ATTRIBUTE3": ["tp attribute 3", "third party attribute 3"],
    "TP_ATTRIBUTE4": ["tp attribute 4", "third party attribute 4"],
    "TP_ATTRIBUTE5": ["tp attribute 5", "third party attribute 5"],
    "TP_ATTRIBUTE6": ["tp attribute 6", "third party attribute 6"],
    "TP_ATTRIBUTE7": ["tp attribute 7", "third party attribute 7"],
    "TP_ATTRIBUTE8": ["tp attribute 8", "third party attribute 8"],
    "TP_ATTRIBUTE9": ["tp attribute 9", "third party attribute 9"],
    "TP_ATTRIBUTE10": ["tp attribute 10", "third party attribute 10"],
    "TP_ATTRIBUTE11": ["tp attribute 11", "third party attribute 11"],
    "TP_ATTRIBUTE12": ["tp attribute 12", "third party attribute 12"],
    "TP_ATTRIBUTE13": ["tp attribute 13", "third party attribute 13"],
    "TP_ATTRIBUTE14": ["tp attribute 14", "third party attribute 14"],
    "TP_ATTRIBUTE15": ["tp attribute 15", "third party attribute 15"],
    "FLOW_STATUS_CODE": ["flow status code", "workflow status code"],
    "MARKETING_SOURCE_CODE_ID": ["marketing source code id", "marketing source code identifier"],
    "CREDIT_CARD_APPROVAL_DATE": ["credit card approval date", "card approval date"],
    "UPGRADED_FLAG": ["upgraded flag", "upgrade status"],
    "CUSTOMER_PREFERENCE_SET_CODE": ["customer preference set code", "customer preference set"],
    "BOOKED_DATE": ["booked date", "booking date"],
    "LOCK_CONTROL": ["lock control", "record lock"],
    "PRICE_REQUEST_CODE": ["price request code", "pricing request code"],
    "BATCH_ID": ["batch id", "batch identifier"],
    "XML_MESSAGE_ID": ["xml message id", "xml message identifier"],
    "ACCOUNTING_RULE_DURATION": ["accounting rule duration", "accounting duration"],
    "ATTRIBUTE16": ["attribute 16", "flexfield attribute 16"],
    "ATTRIBUTE17": ["attribute 17", "flexfield attribute 17"],
    "ATTRIBUTE18": ["attribute 18", "flexfield attribute 18"],
    "ATTRIBUTE19": ["attribute 19", "flexfield attribute 19"],
    "ATTRIBUTE20": ["attribute 20", "flexfield attribute 20"],
    "BLANKET_NUMBER": ["blanket number", "blanket order number"],
    "SALES_DOCUMENT_TYPE_CODE": ["sales document type code", "sales document type"],
    "SOLD_TO_PHONE_ID": ["sold to phone id", "customer phone id"],
    "FULFILLMENT_SET_NAME": ["fulfillment set name", "fulfillment set"],
    "LINE_SET_NAME": ["line set name", "line set"],
    "DEFAULT_FULFILLMENT_SET": ["default fulfillment set", "default fulfillment"],
    "TRANSACTION_PHASE_CODE": ["transaction phase code", "transaction phase"],
    "SALES_DOCUMENT_NAME": ["sales document name", "sales document"],
    "QUOTE_NUMBER": ["quote number", "quotation number"],
    "QUOTE_DATE": ["quote date", "quotation date"],
    "USER_STATUS_CODE": ["user status code", "user status"],
    "DRAFT_SUBMITTED_FLAG": ["draft submitted flag", "draft submission flag"],
    "SOURCE_DOCUMENT_VERSION_NUMBER": ["source document version number", "source document version"],
    "SOLD_TO_SITE_USE_ID": ["sold to site use id", "customer site use id"],
    "SUPPLIER_SIGNATURE": ["supplier signature", "vendor signature"],
    "SUPPLIER_SIGNATURE_DATE": ["supplier signature date", "vendor signature date"],
    "CUSTOMER_SIGNATURE": ["customer signature", "client signature"],
    "CUSTOMER_SIGNATURE_DATE": ["customer signature date", "client signature date"],
    "MINISITE_ID": ["minisite id", "minisite identifier"],
    "END_CUSTOMER_ID": ["end customer id", "end customer identifier"],
    "END_CUSTOMER_CONTACT_ID": ["end customer contact id", "end customer contact identifier"],
    "END_CUSTOMER_SITE_USE_ID": ["end customer site use id", "end customer site use identifier"],
    "IB_OWNER": ["ib owner", "installed base owner"],
    "IB_CURRENT_LOCATION": ["ib current location", "installed base current location"],
    "IB_INSTALLED_AT_LOCATION": ["ib installed at location", "installed base installed at location"],
    "ORDER_FIRMED_DATE": ["order firmed date", "order confirmation date"],
    "INST_ID": ["inst id", "instance id", "instance identifier"],
    "CSR_USER_ID": ["csr user id", "customer service representative user id"],
    "CANCEL_UNSHIPPED_LINES": ["cancel unshipped lines", "cancel undelivered lines"]
})

# OE_ORDER_LINES_ALL table columns
COLUMN_SYNONYMS.update({
    "LINE_ID": ["line id", "order line id", "sales order line id", "line identifier"],
    "ORG_ID": ["org id", "organization id", "operating unit id"],
    "HEADER_ID": ["header id", "order header id", "sales order header id"],
    "LINE_TYPE_ID": ["line type id", "line type identifier"],
    "LINE_NUMBER": ["line number", "line no", "sales order line number"],
    "ORDERED_ITEM": ["ordered item", "item ordered", "product ordered"],
    "REQUEST_DATE": ["request date", "requested date"],
    "PROMISE_DATE": ["promise date", "delivery promise date"],
    "SCHEDULE_SHIP_DATE": ["schedule ship date", "scheduled ship date", "planned ship date"],
    "ORDER_QUANTITY_UOM": ["order quantity uom", "order quantity unit of measure"],
    "PRICING_QUANTITY": ["pricing quantity", "quantity for pricing"],
    "PRICING_QUANTITY_UOM": ["pricing quantity uom", "pricing quantity unit of measure"],
    "CANCELLED_QUANTITY": ["cancelled quantity", "canceled quantity"],
    "SHIPPED_QUANTITY": ["shipped quantity", "quantity shipped"],
    "ORDERED_QUANTITY": ["ordered quantity", "quantity ordered"],
    "FULFILLED_QUANTITY": ["fulfilled quantity", "quantity fulfilled"],
    "SHIPPING_QUANTITY": ["shipping quantity", "quantity for shipping"],
    "SHIPPING_QUANTITY_UOM": ["shipping quantity uom", "shipping quantity unit of measure"],
    "DELIVERY_LEAD_TIME": ["delivery lead time", "lead time for delivery"],
    "TAX_EXEMPT_FLAG": ["tax exempt flag", "tax exemption flag"],
    "TAX_EXEMPT_NUMBER": ["tax exempt number", "tax exemption number"],
    "TAX_EXEMPT_REASON_CODE": ["tax exempt reason code", "tax exemption reason code"],
    "SHIP_FROM_ORG_ID": ["ship from org id", "ship from organization id"],
    "SHIP_TO_ORG_ID": ["ship to org id", "ship to organization id", "delivery org id"],
    "INVOICE_TO_ORG_ID": ["invoice to org id", "invoice to organization id"],
    "DELIVER_TO_ORG_ID": ["deliver to org id", "deliver to organization id"],
    "SHIP_TO_CONTACT_ID": ["ship to contact id", "ship to contact identifier"],
    "DELIVER_TO_CONTACT_ID": ["deliver to contact id", "deliver to contact identifier"],
    "INVOICE_TO_CONTACT_ID": ["invoice to contact id", "invoice to contact identifier"],
    "INTMED_SHIP_TO_ORG_ID": ["intmed ship to org id", "intermediate ship to organization id"],
    "INTMED_SHIP_TO_CONTACT_ID": ["intmed ship to contact id", "intermediate ship to contact id"],
    "SOLD_FROM_ORG_ID": ["sold from org id", "sold from organization id"],
    "SOLD_TO_ORG_ID": ["sold to org id", "sold to organization id", "customer org id"],
    "CUST_PO_NUMBER": ["cust po number", "customer po number", "customer purchase order number"],
    "SHIP_TOLERANCE_ABOVE": ["ship tolerance above", "shipping tolerance above"],
    "SHIP_TOLERANCE_BELOW": ["ship tolerance below", "shipping tolerance below"],
    "DEMAND_BUCKET_TYPE_CODE": ["demand bucket type code", "demand bucket type"],
    "VEH_CUS_ITEM_CUM_KEY_ID": ["veh cus item cum key id", "vehicle customer item cumulative key id"],
    "RLA_SCHEDULE_TYPE_CODE": ["rla schedule type code", "rla schedule type"],
    "CUSTOMER_DOCK_CODE": ["customer dock code", "customer dock"],
    "CUSTOMER_JOB": ["customer job"],
    "CUSTOMER_PRODUCTION_LINE": ["customer production line", "customer production"],
    "CUST_MODEL_SERIAL_NUMBER": ["cust model serial number", "customer model serial number"],
    "PROJECT_ID": ["project id", "project identifier"],
    "TASK_ID": ["task id", "task identifier"],
    "INVENTORY_ITEM_ID": ["inventory item id", "item id", "inventory item identifier"],
    "TAX_DATE": ["tax date"],
    "TAX_CODE": ["tax code"],
    "TAX_RATE": ["tax rate"],
    "INVOICE_INTERFACE_STATUS_CODE": ["invoice interface status code", "invoice interface status"],
    "DEMAND_CLASS_CODE": ["demand class code", "demand class"],
    "PRICE_LIST_ID": ["price list id", "price list identifier"],
    "PRICING_DATE": ["pricing date", "price date"],
    "SHIPMENT_NUMBER": ["shipment number", "shipment no"],
    "AGREEMENT_ID": ["agreement id", "agreement identifier"],
    "SHIPMENT_PRIORITY_CODE": ["shipment priority code", "shipping priority code"],
    "SHIPPING_METHOD_CODE": ["shipping method code", "shipping method"],
    "FREIGHT_CARRIER_CODE": ["freight carrier code", "freight carrier"],
    "FREIGHT_TERMS_CODE": ["freight terms code", "freight terms"],
    "FOB_POINT_CODE": ["fob point code", "fob point", "freight on board point"],
    "TAX_POINT_CODE": ["tax point code", "tax point"],
    "PAYMENT_TERM_ID": ["payment term id", "payment term identifier"],
    "INVOICING_RULE_ID": ["invoicing rule id", "invoicing rule identifier"],
    "ACCOUNTING_RULE_ID": ["accounting rule id", "accounting rule identifier"],
    "SOURCE_DOCUMENT_TYPE_ID": ["source document type id", "source document type identifier"],
    "ORIG_SYS_DOCUMENT_REF": ["orig sys document ref", "original system document reference"],
    "SOURCE_DOCUMENT_ID": ["source document id", "source document identifier"],
    "ORIG_SYS_LINE_REF": ["orig sys line ref", "original system line reference"],
    "SOURCE_DOCUMENT_LINE_ID": ["source document line id", "source document line identifier"],
    "REFERENCE_LINE_ID": ["reference line id", "reference line identifier"],
    "REFERENCE_TYPE": ["reference type"],
    "REFERENCE_HEADER_ID": ["reference header id", "reference header identifier"],
    "ITEM_REVISION": ["item revision", "revision"],
    "UNIT_SELLING_PRICE": ["unit selling price", "selling price per unit"],
    "UNIT_LIST_PRICE": ["unit list price", "list price per unit"],
    "TAX_VALUE": ["tax value", "tax amount"],
    "CONTEXT": ["context", "descriptive flexfield context"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE_CATEGORY": ["global attribute category", "global flexfield category"],
    "GLOBAL_ATTRIBUTE1": ["global attribute 1", "global flexfield attribute 1"],
    "GLOBAL_ATTRIBUTE2": ["global attribute 2", "global flexfield attribute 2"],
    "GLOBAL_ATTRIBUTE3": ["global attribute 3", "global flexfield attribute 3"],
    "GLOBAL_ATTRIBUTE4": ["global attribute 4", "global flexfield attribute 4"],
    "GLOBAL_ATTRIBUTE5": ["global attribute 5", "global flexfield attribute 5"],
    "GLOBAL_ATTRIBUTE6": ["global attribute 6", "global flexfield attribute 6"],
    "GLOBAL_ATTRIBUTE7": ["global attribute 7", "global flexfield attribute 7"],
    "GLOBAL_ATTRIBUTE8": ["global attribute 8", "global flexfield attribute 8"],
    "GLOBAL_ATTRIBUTE9": ["global attribute 9", "global flexfield attribute 9"],
    "GLOBAL_ATTRIBUTE10": ["global attribute 10", "global flexfield attribute 10"],
    "GLOBAL_ATTRIBUTE11": ["global attribute 11", "global flexfield attribute 11"],
    "GLOBAL_ATTRIBUTE12": ["global attribute 12", "global flexfield attribute 12"],
    "GLOBAL_ATTRIBUTE13": ["global attribute 13", "global flexfield attribute 13"],
    "GLOBAL_ATTRIBUTE14": ["global attribute 14", "global flexfield attribute 14"],
    "GLOBAL_ATTRIBUTE15": ["global attribute 15", "global flexfield attribute 15"],
    "GLOBAL_ATTRIBUTE16": ["global attribute 16", "global flexfield attribute 16"],
    "GLOBAL_ATTRIBUTE17": ["global attribute 17", "global flexfield attribute 17"],
    "GLOBAL_ATTRIBUTE18": ["global attribute 18", "global flexfield attribute 18"],
    "GLOBAL_ATTRIBUTE19": ["global attribute 19", "global flexfield attribute 19"],
    "GLOBAL_ATTRIBUTE20": ["global attribute 20", "global flexfield attribute 20"],
    "PRICING_CONTEXT": ["pricing context"],
    "PRICING_ATTRIBUTE1": ["pricing attribute 1"],
    "PRICING_ATTRIBUTE2": ["pricing attribute 2"],
    "PRICING_ATTRIBUTE3": ["pricing attribute 3"],
    "PRICING_ATTRIBUTE4": ["pricing attribute 4"],
    "PRICING_ATTRIBUTE5": ["pricing attribute 5"],
    "PRICING_ATTRIBUTE6": ["pricing attribute 6"],
    "PRICING_ATTRIBUTE7": ["pricing attribute 7"],
    "PRICING_ATTRIBUTE8": ["pricing attribute 8"],
    "PRICING_ATTRIBUTE9": ["pricing attribute 9"],
    "PRICING_ATTRIBUTE10": ["pricing attribute 10"],
    "INDUSTRY_CONTEXT": ["industry context"],
    "INDUSTRY_ATTRIBUTE1": ["industry attribute 1"],
    "INDUSTRY_ATTRIBUTE2": ["industry attribute 2"],
    "INDUSTRY_ATTRIBUTE3": ["industry attribute 3"],
    "INDUSTRY_ATTRIBUTE4": ["industry attribute 4"],
    "INDUSTRY_ATTRIBUTE5": ["industry attribute 5"],
    "INDUSTRY_ATTRIBUTE6": ["industry attribute 6"],
    "INDUSTRY_ATTRIBUTE7": ["industry attribute 7"],
    "INDUSTRY_ATTRIBUTE8": ["industry attribute 8"],
    "INDUSTRY_ATTRIBUTE9": ["industry attribute 9"],
    "INDUSTRY_ATTRIBUTE10": ["industry attribute 10"],
    "INDUSTRY_ATTRIBUTE11": ["industry attribute 11"],
    "INDUSTRY_ATTRIBUTE12": ["industry attribute 12"],
    "INDUSTRY_ATTRIBUTE13": ["industry attribute 13"],
    "INDUSTRY_ATTRIBUTE14": ["industry attribute 14"],
    "INDUSTRY_ATTRIBUTE15": ["industry attribute 15"],
    "INDUSTRY_ATTRIBUTE16": ["industry attribute 16"],
    "INDUSTRY_ATTRIBUTE17": ["industry attribute 17"],
    "INDUSTRY_ATTRIBUTE18": ["industry attribute 18"],
    "INDUSTRY_ATTRIBUTE19": ["industry attribute 19"],
    "INDUSTRY_ATTRIBUTE20": ["industry attribute 20"],
    "INDUSTRY_ATTRIBUTE21": ["industry attribute 21"],
    "INDUSTRY_ATTRIBUTE22": ["industry attribute 22"],
    "INDUSTRY_ATTRIBUTE23": ["industry attribute 23"],
    "INDUSTRY_ATTRIBUTE24": ["industry attribute 24"],
    "INDUSTRY_ATTRIBUTE25": ["industry attribute 25"],
    "INDUSTRY_ATTRIBUTE26": ["industry attribute 26"],
    "INDUSTRY_ATTRIBUTE27": ["industry attribute 27"],
    "INDUSTRY_ATTRIBUTE28": ["industry attribute 28"],
    "INDUSTRY_ATTRIBUTE29": ["industry attribute 29"],
    "INDUSTRY_ATTRIBUTE30": ["industry attribute 30"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "CREATED_BY": ["created by", "creator"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "LAST_UPDATED_BY": ["last updated by", "modifier"],
    "LAST_UPDATE_LOGIN": ["last update login", "login"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id"],
    "PROGRAM_ID": ["program id", "program identifier"],
    "PROGRAM_UPDATE_DATE": ["program update date", "program update"],
    "REQUEST_ID": ["request id", "request identifier"],
    "TOP_MODEL_LINE_ID": ["top model line id", "top model line identifier"],
    "LINK_TO_LINE_ID": ["link to line id", "link to line identifier"],
    "COMPONENT_SEQUENCE_ID": ["component sequence id", "component sequence identifier"],
    "COMPONENT_CODE": ["component code"],
    "CONFIG_DISPLAY_SEQUENCE": ["config display sequence", "configuration display sequence"],
    "SORT_ORDER": ["sort order"],
    "ITEM_TYPE_CODE": ["item type code", "item type"],
    "OPTION_NUMBER": ["option number", "option no"],
    "OPTION_FLAG": ["option flag", "option status"],
    "DEP_PLAN_REQUIRED_FLAG": ["dep plan required flag", "dependency plan required flag"],
    "VISIBLE_DEMAND_FLAG": ["visible demand flag", "visible demand"],
    "LINE_CATEGORY_CODE": ["line category code", "line category"],
    "ACTUAL_SHIPMENT_DATE": ["actual shipment date", "actual ship date"],
    "CUSTOMER_TRX_LINE_ID": ["customer trx line id", "customer transaction line id"],
    "RETURN_CONTEXT": ["return context"],
    "RETURN_ATTRIBUTE1": ["return attribute 1"],
    "RETURN_ATTRIBUTE2": ["return attribute 2"],
    "RETURN_ATTRIBUTE3": ["return attribute 3"],
    "RETURN_ATTRIBUTE4": ["return attribute 4"],
    "RETURN_ATTRIBUTE5": ["return attribute 5"],
    "RETURN_ATTRIBUTE6": ["return attribute 6"],
    "RETURN_ATTRIBUTE7": ["return attribute 7"],
    "RETURN_ATTRIBUTE8": ["return attribute 8"],
    "RETURN_ATTRIBUTE9": ["return attribute 9"],
    "RETURN_ATTRIBUTE10": ["return attribute 10"],
    "RETURN_ATTRIBUTE11": ["return attribute 11"],
    "RETURN_ATTRIBUTE12": ["return attribute 12"],
    "RETURN_ATTRIBUTE13": ["return attribute 13"],
    "RETURN_ATTRIBUTE14": ["return attribute 14"],
    "RETURN_ATTRIBUTE15": ["return attribute 15"],
    "ACTUAL_ARRIVAL_DATE": ["actual arrival date", "actual delivery date"],
    "ATO_LINE_ID": ["ato line id", "ato line identifier", "assemble to order line id"],
    "AUTO_SELECTED_QUANTITY": ["auto selected quantity", "auto selected qty"],
    "COMPONENT_NUMBER": ["component number", "component no"],
    "EARLIEST_ACCEPTABLE_DATE": ["earliest acceptable date", "earliest acceptable delivery date"],
    "EXPLOSION_DATE": ["explosion date"],
    "LATEST_ACCEPTABLE_DATE": ["latest acceptable date", "latest acceptable delivery date"],
    "MODEL_GROUP_NUMBER": ["model group number", "model group no"],
    "SCHEDULE_ARRIVAL_DATE": ["schedule arrival date", "scheduled arrival date"],
    "SHIP_MODEL_COMPLETE_FLAG": ["ship model complete flag", "ship model complete status"],
    "SCHEDULE_STATUS_CODE": ["schedule status code", "schedule status"],
    "SOURCE_TYPE_CODE": ["source type code", "source type"],
    "CANCELLED_FLAG": ["cancelled flag", "canceled flag", "cancel status"],
    "OPEN_FLAG": ["open flag", "open status"],
    "BOOKED_FLAG": ["booked flag", "booked status"],
    "SALESREP_ID": ["salesrep id", "sales rep id", "sales representative id"],
    "RETURN_REASON_CODE": ["return reason code", "return reason"],
    "ARRIVAL_SET_ID": ["arrival set id", "arrival set identifier"],
    "SHIP_SET_ID": ["ship set id", "ship set identifier"],
    "SPLIT_FROM_LINE_ID": ["split from line id", "split from line identifier"],
    "CUST_PRODUCTION_SEQ_NUM": ["cust production seq num", "customer production sequence number"],
    "AUTHORIZED_TO_SHIP_FLAG": ["authorized to ship flag", "authorized to ship status"],
    "OVER_SHIP_REASON_CODE": ["over ship reason code", "over ship reason"],
    "OVER_SHIP_RESOLVED_FLAG": ["over ship resolved flag", "over ship resolved status"],
    "ORDERED_ITEM_ID": ["ordered item id", "ordered item identifier"],
    "ITEM_IDENTIFIER_TYPE": ["item identifier type", "item id type"],
    "CONFIGURATION_ID": ["configuration id", "configuration identifier"],
    "COMMITMENT_ID": ["commitment id", "commitment identifier"],
    "SHIPPING_INTERFACED_FLAG": ["shipping interfaced flag", "shipping interfaced status"],
    "CREDIT_INVOICE_LINE_ID": ["credit invoice line id", "credit invoice line identifier"],
    "FIRST_ACK_CODE": ["first ack code", "first acknowledgment code"],
    "FIRST_ACK_DATE": ["first ack date", "first acknowledgment date"],
    "LAST_ACK_CODE": ["last ack code", "last acknowledgment code"],
    "LAST_ACK_DATE": ["last ack date", "last acknowledgment date"],
    "PLANNING_PRIORITY": ["planning priority"],
    "ORDER_SOURCE_ID": ["order source id", "order source identifier"],
    "ORIG_SYS_SHIPMENT_REF": ["orig sys shipment ref", "original system shipment reference"],
    "CHANGE_SEQUENCE": ["change sequence", "sequence number"],
    "DROP_SHIP_FLAG": ["drop ship flag", "drop shipment flag"],
    "CUSTOMER_LINE_NUMBER": ["customer line number", "customer line no"],
    "CUSTOMER_SHIPMENT_NUMBER": ["customer shipment number", "customer shipment no"],
    "CUSTOMER_ITEM_NET_PRICE": ["customer item net price", "customer net price"],
    "CUSTOMER_PAYMENT_TERM_ID": ["customer payment term id", "customer payment term identifier"],
    "FULFILLED_FLAG": ["fulfilled flag", "fulfilled status"],
    "END_ITEM_UNIT_NUMBER": ["end item unit number", "end item unit no"],
    "CONFIG_HEADER_ID": ["config header id", "configuration header id"],
    "CONFIG_REV_NBR": ["config rev nbr", "configuration revision number"],
    "MFG_COMPONENT_SEQUENCE_ID": ["mfg component sequence id", "manufacturing component sequence id"],
    "SHIPPING_INSTRUCTIONS": ["shipping instructions", "delivery instructions"],
    "PACKING_INSTRUCTIONS": ["packing instructions", "packaging instructions"],
    "INVOICED_QUANTITY": ["invoiced quantity", "quantity invoiced"],
    "REFERENCE_CUSTOMER_TRX_LINE_ID": ["reference customer trx line id", "reference customer transaction line id"],
    "SPLIT_BY": ["split by"],
    "LINE_SET_ID": ["line set id", "line set identifier"],
    "SERVICE_TXN_REASON_CODE": ["service txn reason code", "service transaction reason code"],
    "SERVICE_TXN_COMMENTS": ["service txn comments", "service transaction comments"],
    "SERVICE_DURATION": ["service duration"],
    "SERVICE_START_DATE": ["service start date", "service start"],
    "SERVICE_END_DATE": ["service end date", "service end"],
    "SERVICE_COTERMINATE_FLAG": ["service coterminate flag", "service coterminate status"],
    "UNIT_LIST_PERCENT": ["unit list percent", "unit list percentage"],
    "UNIT_SELLING_PERCENT": ["unit selling percent", "unit selling percentage"],
    "UNIT_PERCENT_BASE_PRICE": ["unit percent base price", "unit percentage base price"],
    "SERVICE_NUMBER": ["service number", "service no"],
    "SERVICE_PERIOD": ["service period"],
    "SHIPPABLE_FLAG": ["shippable flag", "shippable status"],
    "MODEL_REMNANT_FLAG": ["model remnant flag", "model remnant status"],
    "RE_SOURCE_FLAG": ["re source flag", "re source status"],
    "FLOW_STATUS_CODE": ["flow status code", "workflow status code"],
    "TP_CONTEXT": ["tp context", "third party context"],
    "TP_ATTRIBUTE1": ["tp attribute 1", "third party attribute 1"],
    "TP_ATTRIBUTE2": ["tp attribute 2", "third party attribute 2"],
    "TP_ATTRIBUTE3": ["tp attribute 3", "third party attribute 3"],
    "TP_ATTRIBUTE4": ["tp attribute 4", "third party attribute 4"],
    "TP_ATTRIBUTE5": ["tp attribute 5", "third party attribute 5"],
    "TP_ATTRIBUTE6": ["tp attribute 6", "third party attribute 6"],
    "TP_ATTRIBUTE7": ["tp attribute 7", "third party attribute 7"],
    "TP_ATTRIBUTE8": ["tp attribute 8", "third party attribute 8"],
    "TP_ATTRIBUTE9": ["tp attribute 9", "third party attribute 9"],
    "TP_ATTRIBUTE10": ["tp attribute 10", "third party attribute 10"],
    "TP_ATTRIBUTE11": ["tp attribute 11", "third party attribute 11"],
    "TP_ATTRIBUTE12": ["tp attribute 12", "third party attribute 12"],
    "TP_ATTRIBUTE13": ["tp attribute 13", "third party attribute 13"],
    "TP_ATTRIBUTE14": ["tp attribute 14", "third party attribute 14"],
    "TP_ATTRIBUTE15": ["tp attribute 15", "third party attribute 15"],
    "FULFILLMENT_METHOD_CODE": ["fulfillment method code", "fulfillment method"],
    "MARKETING_SOURCE_CODE_ID": ["marketing source code id", "marketing source code identifier"],
    "SERVICE_REFERENCE_TYPE_CODE": ["service reference type code", "service reference type"],
    "SERVICE_REFERENCE_LINE_ID": ["service reference line id", "service reference line identifier"],
    "SERVICE_REFERENCE_SYSTEM_ID": ["service reference system id", "service reference system identifier"],
    "CALCULATE_PRICE_FLAG": ["calculate price flag", "calculate price status"],
    "UPGRADED_FLAG": ["upgraded flag", "upgrade status"],
    "REVENUE_AMOUNT": ["revenue amount", "revenue"],
    "FULFILLMENT_DATE": ["fulfillment date"],
    "PREFERRED_GRADE": ["preferred grade"],
    "ORDERED_QUANTITY2": ["ordered quantity 2", "ordered quantity secondary"],
    "ORDERED_QUANTITY_UOM2": ["ordered quantity uom 2", "ordered quantity unit of measure 2"],
    "SHIPPING_QUANTITY2": ["shipping quantity 2", "shipping quantity secondary"],
    "CANCELLED_QUANTITY2": ["cancelled quantity 2", "cancelled quantity secondary"],
    "SHIPPED_QUANTITY2": ["shipped quantity 2", "shipped quantity secondary"],
    "SHIPPING_QUANTITY_UOM2": ["shipping quantity uom 2", "shipping quantity unit of measure 2"],
    "FULFILLED_QUANTITY2": ["fulfilled quantity 2", "fulfilled quantity secondary"],
    "MFG_LEAD_TIME": ["mfg lead time", "manufacturing lead time"],
    "LOCK_CONTROL": ["lock control", "record lock"],
    "SUBINVENTORY": ["subinventory", "subinv"],
    "UNIT_LIST_PRICE_PER_PQTY": ["unit list price per pqty", "unit list price per pricing quantity"],
    "UNIT_SELLING_PRICE_PER_PQTY": ["unit selling price per pqty", "unit selling price per pricing quantity"],
    "PRICE_REQUEST_CODE": ["price request code", "pricing request code"],
    "ORIGINAL_INVENTORY_ITEM_ID": ["original inventory item id", "original item id"],
    "ORIGINAL_ORDERED_ITEM_ID": ["original ordered item id", "original ordered item identifier"],
    "ORIGINAL_ORDERED_ITEM": ["original ordered item"],
    "ORIGINAL_ITEM_IDENTIFIER_TYPE": ["original item identifier type", "original item id type"],
    "ITEM_SUBSTITUTION_TYPE_CODE": ["item substitution type code", "item substitution type"],
    "OVERRIDE_ATP_DATE_CODE": ["override atp date code", "override atp date"],
    "LATE_DEMAND_PENALTY_FACTOR": ["late demand penalty factor", "late demand penalty"],
    "ACCOUNTING_RULE_DURATION": ["accounting rule duration", "accounting duration"],
    "ATTRIBUTE16": ["attribute 16", "flexfield attribute 16"],
    "ATTRIBUTE17": ["attribute 17", "flexfield attribute 17"],
    "ATTRIBUTE18": ["attribute 18", "flexfield attribute 18"],
    "ATTRIBUTE19": ["attribute 19", "flexfield attribute 19"],
    "ATTRIBUTE20": ["attribute 20", "flexfield attribute 20"],
    "USER_ITEM_DESCRIPTION": ["user item description", "item description"],
    "UNIT_COST": ["unit cost", "cost per unit"],
    "ITEM_RELATIONSHIP_TYPE": ["item relationship type", "item relationship"],
    "BLANKET_LINE_NUMBER": ["blanket line number", "blanket line no"],
    "BLANKET_NUMBER": ["blanket number", "blanket order number"],
    "BLANKET_VERSION_NUMBER": ["blanket version number", "blanket version"],
    "SALES_DOCUMENT_TYPE_CODE": ["sales document type code", "sales document type"],
    "FIRM_DEMAND_FLAG": ["firm demand flag", "firm demand status"],
    "EARLIEST_SHIP_DATE": ["earliest ship date", "earliest shipping date"],
    "TRANSACTION_PHASE_CODE": ["transaction phase code", "transaction phase"],
    "SOURCE_DOCUMENT_VERSION_NUMBER": ["source document version number", "source document version"],
    "PAYMENT_TYPE_CODE": ["payment type code", "payment type"],
    "MINISITE_ID": ["minisite id", "minisite identifier"],
    "END_CUSTOMER_ID": ["end customer id", "end customer identifier"],
    "END_CUSTOMER_CONTACT_ID": ["end customer contact id", "end customer contact identifier"],
    "END_CUSTOMER_SITE_USE_ID": ["end customer site use id", "end customer site use identifier"],
    "IB_OWNER": ["ib owner", "installed base owner"],
    "IB_CURRENT_LOCATION": ["ib current location", "installed base current location"],
    "IB_INSTALLED_AT_LOCATION": ["ib installed at location", "installed base installed at location"],
    "RETROBILL_REQUEST_ID": ["retrobill request id", "retrobill request identifier"],
    "ORIGINAL_LIST_PRICE": ["original list price", "original list"],
    "SERVICE_CREDIT_ELIGIBLE_CODE": ["service credit eligible code", "service credit eligible"],
    "ORDER_FIRMED_DATE": ["order firmed date", "order confirmation date"],
    "ACTUAL_FULFILLMENT_DATE": ["actual fulfillment date", "actual fulfillment"],
    "CHARGE_PERIODICITY_CODE": ["charge periodicity code", "charge periodicity"],
    "CONTINGENCY_ID": ["contingency id", "contingency identifier"],
    "REVREC_EVENT_CODE": ["revrec event code", "revenue recognition event code"],
    "REVREC_EXPIRATION_DAYS": ["revrec expiration days", "revenue recognition expiration days"],
    "ACCEPTED_QUANTITY": ["accepted quantity", "quantity accepted"],
    "ACCEPTED_BY": ["accepted by"],
    "REVREC_COMMENTS": ["revrec comments", "revenue recognition comments"],
    "REVREC_REFERENCE_DOCUMENT": ["revrec reference document", "revenue recognition reference document"],
    "REVREC_SIGNATURE": ["revrec signature", "revenue recognition signature"],
    "REVREC_SIGNATURE_DATE": ["revrec signature date", "revenue recognition signature date"],
    "REVREC_IMPLICIT_FLAG": ["revrec implicit flag", "revenue recognition implicit flag"],
    "BYPASS_SCH_FLAG": ["bypass sch flag", "bypass schedule flag"],
    "PRE_EXPLODED_FLAG": ["pre exploded flag", "pre exploded status"],
    "INST_ID": ["inst id", "instance id", "instance identifier"],
    "TAX_LINE_VALUE": ["tax line value", "tax line amount"],
    "SERVICE_BILL_PROFILE_ID": ["service bill profile id", "service bill profile identifier"],
    "SERVICE_COV_TEMPLATE_ID": ["service cov template id", "service coverage template id"],
    "SERVICE_SUBS_TEMPLATE_ID": ["service subs template id", "service subscription template id"],
    "SERVICE_BILL_OPTION_CODE": ["service bill option code", "service bill option"],
    "SERVICE_FIRST_PERIOD_AMOUNT": ["service first period amount", "service first period"],
    "SERVICE_FIRST_PERIOD_ENDDATE": ["service first period enddate", "service first period end date"],
    "SUBSCRIPTION_ENABLE_FLAG": ["subscription enable flag", "subscription enable status"],
    "FULFILLMENT_BASE": ["fulfillment base"],
    "CONTAINER_NUMBER": ["container number", "container no"],
    "EQUIPMENT_ID": ["equipment id", "equipment identifier"],
    "REQUIRE_BILLING_VALIDATION": ["require billing validation", "billing validation required"],
    "BILLING_PLAN_HEADER_ID": ["billing plan header id", "billing plan header identifier"],
    "SOURCE_ORDER_LINE_ID": ["source order line id", "source order line identifier"],
    "VRM_LAST_UPDATE_DATE": ["vrm last update date", "vrm last update"]
})

# OE_TRANSACTION_TYPES_ALL table columns
COLUMN_SYNONYMS.update({
    "TRANSACTION_TYPE_ID": ["transaction type id", "transaction type identifier"],
    "TRANSACTION_TYPE_CODE": ["transaction type code", "transaction type"],
    "ORDER_CATEGORY_CODE": ["order category code", "order category"],
    "START_DATE_ACTIVE": ["start date active", "start date", "active start date"],
    "END_DATE_ACTIVE": ["end date active", "end date", "active end date"],
    "CREATION_DATE": ["creation date", "created date", "create date"],
    "CREATED_BY": ["created by", "creator"],
    "LAST_UPDATE_DATE": ["last update date", "modified date", "update date"],
    "LAST_UPDATED_BY": ["last updated by", "modifier"],
    "LAST_UPDATE_LOGIN": ["last update login", "login"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id"],
    "PROGRAM_ID": ["program id", "program identifier"],
    "REQUEST_ID": ["request id", "request identifier"],
    "CURRENCY_CODE": ["currency code", "currency"],
    "CONVERSION_TYPE_CODE": ["conversion type code", "currency conversion type code"],
    "CUST_TRX_TYPE_ID": ["cust trx type id", "customer transaction type id"],
    "COST_OF_GOODS_SOLD_ACCOUNT": ["cost of goods sold account", "cogs account"],
    "ENTRY_CREDIT_CHECK_RULE_ID": ["entry credit check rule id", "entry credit check rule identifier"],
    "SHIPPING_CREDIT_CHECK_RULE_ID": ["shipping credit check rule id", "shipping credit check rule identifier"],
    "PRICE_LIST_ID": ["price list id", "price list identifier"],
    "ENFORCE_LINE_PRICES_FLAG": ["enforce line prices flag", "enforce line prices"],
    "WAREHOUSE_ID": ["warehouse id", "warehouse identifier"],
    "DEMAND_CLASS_CODE": ["demand class code", "demand class"],
    "SHIPMENT_PRIORITY_CODE": ["shipment priority code", "shipping priority code"],
    "SHIPPING_METHOD_CODE": ["shipping method code", "shipping method"],
    "FREIGHT_TERMS_CODE": ["freight terms code", "freight terms"],
    "FOB_POINT_CODE": ["fob point code", "fob point", "freight on board point"],
    "SHIP_SOURCE_TYPE_CODE": ["ship source type code", "ship source type"],
    "AGREEMENT_TYPE_CODE": ["agreement type code", "agreement type"],
    "AGREEMENT_REQUIRED_FLAG": ["agreement required flag", "agreement required"],
    "PO_REQUIRED_FLAG": ["po required flag", "purchase order required flag"],
    "INVOICING_RULE_ID": ["invoicing rule id", "invoicing rule identifier"],
    "INVOICING_CREDIT_METHOD_CODE": ["invoicing credit method code", "invoicing credit method"],
    "ACCOUNTING_RULE_ID": ["accounting rule id", "accounting rule identifier"],
    "ACCOUNTING_CREDIT_METHOD_CODE": ["accounting credit method code", "accounting credit method"],
    "INVOICE_SOURCE_ID": ["invoice source id", "invoice source identifier"],
    "NON_DELIVERY_INVOICE_SOURCE_ID": ["non delivery invoice source id", "non delivery invoice source identifier"],
    "INSPECTION_REQUIRED_FLAG": ["inspection required flag", "inspection required"],
    "DEPOT_REPAIR_CODE": ["depot repair code", "depot repair"],
    "ORG_ID": ["org id", "organization id", "operating unit id"],
    "AUTO_SCHEDULING_FLAG": ["auto scheduling flag", "auto scheduling"],
    "SCHEDULING_LEVEL_CODE": ["scheduling level code", "scheduling level"],
    "CONTEXT": ["context", "descriptive flexfield context"],
    "ATTRIBUTE1": ["attribute 1", "flexfield attribute 1"],
    "ATTRIBUTE2": ["attribute 2", "flexfield attribute 2"],
    "ATTRIBUTE3": ["attribute 3", "flexfield attribute 3"],
    "ATTRIBUTE4": ["attribute 4", "flexfield attribute 4"],
    "ATTRIBUTE5": ["attribute 5", "flexfield attribute 5"],
    "ATTRIBUTE6": ["attribute 6", "flexfield attribute 6"],
    "ATTRIBUTE7": ["attribute 7", "flexfield attribute 7"],
    "ATTRIBUTE8": ["attribute 8", "flexfield attribute 8"],
    "ATTRIBUTE9": ["attribute 9", "flexfield attribute 9"],
    "ATTRIBUTE10": ["attribute 10", "flexfield attribute 10"],
    "ATTRIBUTE11": ["attribute 11", "flexfield attribute 11"],
    "ATTRIBUTE12": ["attribute 12", "flexfield attribute 12"],
    "ATTRIBUTE13": ["attribute 13", "flexfield attribute 13"],
    "ATTRIBUTE14": ["attribute 14", "flexfield attribute 14"],
    "ATTRIBUTE15": ["attribute 15", "flexfield attribute 15"],
    "DEFAULT_INBOUND_LINE_TYPE_ID": ["default inbound line type id", "default inbound line type identifier"],
    "DEFAULT_OUTBOUND_LINE_TYPE_ID": ["default outbound line type id", "default outbound line type identifier"],
    "TAX_CALCULATION_EVENT_CODE": ["tax calculation event code", "tax calculation event"],
    "PICKING_CREDIT_CHECK_RULE_ID": ["picking credit check rule id", "picking credit check rule identifier"],
    "PACKING_C": ["packing c", "packing credit check rule"],
    "MIN_MARGIN_PERCENT": ["min margin percent", "minimum margin percentage"],
    "SALES_DOCUMENT_TYPE_CODE": ["sales document type code", "sales document type"],
    "DEFAULT_LINE_SET_CODE": ["default line set code", "default line set"],
    "DEFAULT_FULFILLMENT_SET": ["default fulfillment set", "default fulfillment"],
    "DEF_TRANSACTION_PHASE_CODE": ["def transaction phase code", "default transaction phase code"],
    "QUOTE_NUM_AS_ORD_NUM_FLAG": ["quote num as ord num flag", "quote number as order number flag"],
    "LAYOUT_TEMPLATE_ID": ["layout template id", "layout template identifier"],
    "CONTRACT_TEMPLATE_ID": ["contract template id", "contract template identifier"],
    "CREDIT_CARD_REV_REAUTH_CODE": ["credit card rev reauth code", "credit card reversal reauthorization code"],
    "USE_AME_APPROVAL": ["use ame approval", "use approval management engine approval"],
    "BILL_ONLY": ["bill only", "bill only flag"],
    
    # WSH_DELIVERY_ASSIGNMENTS table columns
    "DELIVERY_ASSIGNMENT_ID": ["delivery assignment id", "delivery assignment identifier", "assignment id"],
    "DELIVERY_ID": ["delivery id", "delivery identifier", "shipment id", "shipment identifier"],
    "PARENT_DELIVERY_ID": ["parent delivery id", "parent delivery identifier", "parent shipment id"],
    "DELIVERY_DETAIL_ID": ["delivery detail id", "delivery detail identifier", "shipment detail id"],
    "PARENT_DELIVERY_DETAIL_ID": ["parent delivery detail id", "parent delivery detail identifier", "parent shipment detail id"],
    "CREATION_DATE": ["creation date", "created date", "date created"],
    "CREATED_BY": ["created by", "created by user", "user created"],
    "LAST_UPDATE_DATE": ["last update date", "updated date", "date updated", "modified date"],
    "LAST_UPDATED_BY": ["last updated by", "updated by", "modified by"],
    "LAST_UPDATE_LOGIN": ["last update login", "update login", "login id"],
    "PROGRAM_APPLICATION_ID": ["program application id", "program app id", "concurrent program application id"],
    "PROGRAM_ID": ["program id", "concurrent program id"],
    "PROGRAM_UPDATE_DATE": ["program update date", "concurrent program update date"],
    "REQUEST_ID": ["request id", "concurrent request id"],
    "ACTIVE_FLAG": ["active flag", "is active", "currently active", "status"],
    "TYPE": ["type", "assignment type", "delivery assignment type"]
})

def _contains_phrase(q: str, phrase: str) -> bool:
    return phrase.lower() in q

def expand_query_with_synonyms(query: str) -> str:
    """
    Expand the user query with canonical tokens when a synonym/alias is detected.
    Keeps the index lean and improves recall without reindexing.
    
    For ERP R12, this specifically enhances matching for:
    - Core table names: HR_OPERATING_UNITS, ORG_ORGANIZATION_DEFINITIONS
    - Key column names with their business meanings
    - Relationship terms between tables
    """
    if not ENABLE_QUERY_SYNONYMS or not query:
        return query

    ql = query.lower()
    added = set()
    extras = []

    for canonical, syns in COLUMN_SYNONYMS.items():
        canon_l = canonical.lower()
        if canon_l in ql:
            continue
        if any(_contains_phrase(ql, s.lower()) for s in syns):
            if canonical not in added:
                # Add contextual hints for key relationships
                if canonical in ["ORGANIZATION_ID", "OPERATING_UNIT"]:
                    # These columns establish the key relationship between tables
                    extras.append("HR_OPERATING_UNITS.ORGANIZATION_ID=ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT")
                elif canonical in ["ORGANIZATION_ID"]:
                    # Check if this is for MTL tables
                    if any(term in ql for term in ["onhand", "subinventory", "inventory"]):
                        extras.append("MTL_ONHAND_QUANTITIES_DETAIL.ORGANIZATION_ID=ORG_ORGANIZATION_DEFINITIONS.ORGANIZATION_ID")
                        extras.append("MTL_SECONDARY_INVENTORIES.ORGANIZATION_ID=ORG_ORGANIZATION_DEFINITIONS.ORGANIZATION_ID")
                    # Check if this is for MTL_DEMAND table
                    elif any(term in ql for term in ["demand", "material demand", "requirement"]):
                        extras.append("MTL_DEMAND.ORGANIZATION_ID=ORG_ORGANIZATION_DEFINITIONS.ORGANIZATION_ID")
                    # Check if this is for MTL_ITEM_LOCATIONS table
                    elif any(term in ql for term in ["item locations", "locator", "warehouse", "physical locations", "storage"]):
                        extras.append("MTL_ITEM_LOCATIONS.ORGANIZATION_ID=ORG_ORGANIZATION_DEFINITIONS.ORGANIZATION_ID")
                extras.append(canonical)
                added.add(canonical)

    if not extras:
        return query

    expanded = query + " " + " ".join(extras)
    logger.debug(f"[ERP QuerySynonyms] Expanded query: '{query}' → '{expanded}'")
    return expanded

def needs_join(query: str) -> bool:
    """
    Dynamically determine if a query requires joining HR_OPERATING_UNITS and ORG_ORGANIZATION_DEFINITIONS
    based on natural language understanding without hardcoding specific patterns.
    
    Args:
        query: The user's natural language query
        
    Returns:
        True if a join is needed, False otherwise
    """
    if not query:
        return False
        
    ql = query.lower()
    
    # Dynamic detection based on semantic understanding
    # Check for terms that indicate cross-table requests
    join_indicators = ["join", "link", "connect", "both", "together", "with", "and"]
    has_join_indicator = any(indicator in ql for indicator in join_indicators)
    
    # Check for conceptual entity references
    operating_unit_concepts = ["operating unit", "short code", "business group", "usable flag", "set of books"]
    organization_concepts = ["organization", "organization name", "organization code", "inventory enabled", "chart of accounts"]
    
    has_operating_unit_concept = any(concept in ql for concept in operating_unit_concepts)
    has_organization_concept = any(concept in ql for concept in organization_concepts)
    
    # Dynamic join detection based on cross-entity requests
    if "both" in ql and (has_operating_unit_concept or has_organization_concept):
        return True
        
    if has_join_indicator and has_operating_unit_concept and has_organization_concept:
        return True
        
    # If query asks for data from different conceptual entities, we need a join
    if has_operating_unit_concept and has_organization_concept:
        return True
        
    # Special pattern: queries asking for specific ID values with data from both tables
    if "id" in ql and has_operating_unit_concept and has_organization_concept:
        return True
        
    # Pattern: queries specifically asking for "set of books" with "both" tables
    if "set of books" in ql and ("both" in ql or (has_operating_unit_concept and has_organization_concept)):
        return True
        
    # Check for queries that involve both new tables (MTL_ONHAND_QUANTITIES_DETAIL and MTL_SECONDARY_INVENTORIES)
    onhand_concepts = ["onhand", "on-hand", "inventory quantities", "items received", "received this month", "onhand quantity", "inventory quantity"]
    subinventory_concepts = ["subinventory", "secondary inventory", "sub inventories", "subinventory description"]
    
    has_onhand_concept = any(concept in ql for concept in onhand_concepts)
    has_subinventory_concept = any(concept in ql for concept in subinventory_concepts)
    
    if has_onhand_concept and has_subinventory_concept:
        return True
    
    # Check for queries that involve MTL_ONHAND_QUANTITIES_DETAIL and ORG_ORGANIZATION_DEFINITIONS
    organization_concepts = ["organization", "organizations", "org", "org name", "organization name"]
    has_organization_concept = any(concept in ql for concept in organization_concepts)
    
    if has_onhand_concept and has_organization_concept:
        return True
    
    # Check for queries that involve MTL_SECONDARY_INVENTORIES and ORG_ORGANIZATION_DEFINITIONS
    if has_subinventory_concept and has_organization_concept:
        return True
        
    # Check for queries that involve MTL_DEMAND and ORG_ORGANIZATION_DEFINITIONS
    demand_concepts = ["demand", "material demand", "requirement", "demand planning", "inventory demand"]
    has_demand_concept = any(concept in ql for concept in demand_concepts)
    
    if has_demand_concept and has_organization_concept:
        return True
        
    # Check for queries that involve MTL_ITEM_LOCATIONS and ORG_ORGANIZATION_DEFINITIONS
    item_location_concepts = ["item locations", "locator", "warehouse", "physical locations", "storage", "inventory coordinates"]
    has_item_location_concept = any(concept in ql for concept in item_location_concepts)
    
    if has_item_location_concept and has_organization_concept:
        return True
        
    return False

# =========================
# Core search helpers
# =========================
def search_similar_schema(query: str, selected_db: str, top_k: int = 5) -> List[Dict]:
    """
    Search for similar schema documents in the vector store.
    
    For ERP R12, this prioritizes matches for the two core tables:
    - HR_OPERATING_UNITS
    - ORG_ORGANIZATION_DEFINITIONS
    
    And their key columns and relationships.
    """
    client = get_chroma_client(selected_db)
    collection_name = f"schema_docs_{selected_db}"
    collection = client.get_or_create_collection(name=collection_name)

    q_expanded = expand_query_with_synonyms(query)
    query_vector = get_embedding(q_expanded)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas"]  # no "ids" for compatibility
    )

    docs  = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids   = results.get("ids", [[]])[0] if results.get("ids") else [None] * len(docs)

    # Filter results to prioritize actual schema information
    filtered_results = []
    for _id, doc, meta in zip(ids, docs, metas):
        # Only include results that have actual schema information
        if doc and meta and 'kind' in meta:
            # Prioritize column and table information
            if meta.get('kind') in ['column', 'table']:
                filtered_results.append({"id": _id, "document": doc, "metadata": meta})
            # Also include relationship information
            elif 'relationship' in doc.lower() or 'join' in doc.lower():
                filtered_results.append({"id": _id, "document": doc, "metadata": meta})
    
    # If we don't have enough filtered results, include all results
    if len(filtered_results) < top_k // 2:
        for _id, doc, meta in zip(ids, docs, metas):
            if doc and {"id": _id, "document": doc, "metadata": meta} not in filtered_results:
                filtered_results.append({"id": _id, "document": doc, "metadata": meta})
                if len(filtered_results) >= top_k:
                    break
    
    return filtered_results[:top_k]

def search_vector_store_detailed(query: str, selected_db: str, top_k: int = 3) -> List[Dict]:
    """
    Perform detailed vector search with distance scores.
    
    Enhanced for ERP R12 to better understand:
    - Table relationships (HR_OPERATING_UNITS.ORGANIZATION_ID ↔ ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT)
    - Business context terms
    - Column synonyms and aliases
    """
    client = get_chroma_client(selected_db)
    collection_name = f"schema_docs_{selected_db}"

    # Will create an empty collection if missing (harmless), so queries just return [].
    try:
        collection = client.get_or_create_collection(name=collection_name)
    except Exception as e:
        logger.warning(f"[ERP CHROMA] Could not get/create collection '{collection_name}': {e}")
        return []

    q_expanded = expand_query_with_synonyms(query)
    query_vector = get_embedding(q_expanded)

    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["documents", "distances", "metadatas"]  # ids optional in some versions
        )
    except Exception as e:
        logger.warning(f"[ERP CHROMA] Query failed for '{collection_name}': {e}")
        return []

    docs  = results.get("documents", [[]])[0] if results.get("documents") else []
    dists = results.get("distances", [[]])[0] if results.get("distances") else []
    metas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
    ids   = results.get("ids", [[]])[0] if results.get("ids") else [None] * len(docs)

    out: List[Dict] = []
    for doc, dist, meta, _id in zip(docs, dists, metas, ids):
        out.append({
            "id": _id,
            "document": doc,
            "score": dist,
            "metadata": meta
        })
    return out

# ✅ Unified hybrid search used by query_engine.py
def hybrid_schema_value_search(query: str, selected_db: str, top_k: int = 10) -> List[Dict]:
    """
    Simple hybrid: detailed semantic search after query-time expansion.
    
    For ERP R12, this ensures:
    - Proper synonym expansion for business terms
    - Relationship awareness for key table joins
    - Enhanced matching for core ERP concepts
    
    If you add keyword/metadata filtering later, integrate here.
    """
    return search_vector_store_detailed(query, selected_db=selected_db, top_k=top_k)

# ✅ Persist to disk (no-op on PersistentClient; keep for compatibility)
def persist_chroma(selected_db: str):
    """
    Persist ChromaDB changes to disk.
    
    For ERP R12, this ensures schema embeddings are saved for:
    - HR_OPERATING_UNITS table and columns
    - ORG_ORGANIZATION_DEFINITIONS table and columns
    - Relationship metadata between tables
    """
    try:
        client = get_chroma_client(selected_db)
        # Newer Chroma with PersistentClient persists automatically.
        if hasattr(client, "persist"):
            client.persist()  # older versions only
        logger.info(f"[ERP CHROMA] ✅ Changes persisted for DB: {selected_db}")
    except Exception:
        # Swallow quietly; persistence is automatic with PersistentClient
        logger.debug(f"[ERP CHROMA] Persistence handled automatically for {selected_db}")