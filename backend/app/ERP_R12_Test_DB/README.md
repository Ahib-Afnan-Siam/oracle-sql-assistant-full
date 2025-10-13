# ERP R12 Module

This module provides support for Oracle ERP R12 database queries in the Oracle SQL Assistant.

## Overview

The ERP R12 module is designed to handle queries specific to Oracle ERP R12 systems, with a focus on organizational structure tables including:

1. **HR_OPERATING_UNITS** - Contains operating unit definitions
2. **ORG_ORGANIZATION_DEFINITIONS** - Defines organizations and their relationships

## Key Features

### Schema Loading
- Enhanced schema loader with ERP R12 specific column hints
- Business context documentation for critical tables
- Relationship mapping between core ERP tables
- Value sampling for ID-like columns
- Numeric range analysis for numeric columns

### RAG Engine
- ERP-specific entity recognition
- Context-aware SQL generation
- Relationship-aware query building
- Natural language summarization of results

### Query Routing
- Intelligent query routing based on keywords and patterns
- Confidence-based classification
- Fallback mechanisms for ambiguous queries

### Hybrid Processing
- Parallel processing capabilities
- Performance monitoring and statistics
- Error handling and recovery

## Core Tables

### HR_OPERATING_UNITS
Contains operating unit definitions with the following key columns:
- `BUSINESS_GROUP_ID` - Links to business groups
- `ORGANIZATION_ID` - Primary key, links to ORG_ORGANIZATION_DEFINITIONS
- `NAME` - Operating unit name
- `DATE_FROM`/`DATE_TO` - Validity dates
- `USABLE_FLAG` - Usability indicator

### ORG_ORGANIZATION_DEFINITIONS
Defines organizations with these important columns:
- `ORGANIZATION_ID` - Primary key
- `OPERATING_UNIT` - Foreign key to HR_OPERATING_UNITS.ORGANIZATION_ID
- `ORGANIZATION_NAME` - Organization name
- `ORGANIZATION_CODE` - Organization code
- `INVENTORY_ENABLED_FLAG` - Inventory enablement flag

## Relationships

The core relationship between these tables is:
```
HR_OPERATING_UNITS.ORGANIZATION_ID → ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT
```

This relationship is fundamental to ERP R12 organizational structure queries.

## Usage

The module is automatically integrated into the main application and will handle queries containing ERP-specific keywords like:
- "business group"
- "operating unit" 
- "organization"
- "legal entity"
- "ERP"
- "R12"

## Configuration

The module uses the same database configuration as the main application, specifically connecting to `source_db_2` which should be configured with ERP R12 database credentials.

## Testing

Run the schema loader test:
```bash
python test_schema_loader.py
```