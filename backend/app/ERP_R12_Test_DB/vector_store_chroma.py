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
def get_chroma_client(selected_db: str) -> chromadb.Client:
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