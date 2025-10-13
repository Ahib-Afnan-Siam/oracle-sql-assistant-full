# Uttoron - Oracle SQL Assistant

> A sophisticated natural-language-to-SQL system that lets users query **Oracle databases** with conversational input. It pairs advanced AI processing with a user-friendly interface to **generate, execute, and visualize** Oracle SQL from plain English.

## 📋 Table of Contents
- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [ERP R12 Support](#erp-r12-support)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 📖 Overview

Uttoron is an advanced natural language to SQL system designed specifically for Oracle databases. It enables non-technical users to query complex Oracle databases using plain English, eliminating the need for manual SQL writing and reducing dependency on database experts.

The system combines Retrieval-Augmented Generation (RAG) with hybrid AI processing to provide accurate, context-aware SQL generation. It supports both local LLM inference (via Ollama) and cloud-based models (via OpenRouter), allowing for flexible deployment options that balance performance, privacy, and accuracy.

### Core Problems Solved
- Eliminates the need for users to write SQL manually
- Reduces errors in SQL generation through schema-aware AI reasoning
- Supports hybrid AI processing for balancing performance, privacy, and accuracy
- Provides feedback and training mechanisms for continuous model improvement
- Offers specialized support for Oracle ERP R12 systems with deep domain understanding

## ✨ Key Features

### Natural Language Processing
- Convert English queries into executable Oracle SQL
- Dynamic entity recognition for business entities, dates, and codes
- Intent classification for specialized query routing
- Confidence scoring for generated SQL reliability

### AI Processing
- Hybrid AI processing combining local and cloud LLMs
- Parallel execution of multiple models with intelligent selection
- Schema-aware reasoning using vector embeddings
- Contextual understanding of database structures

### Database Integration
- Direct execution against Oracle databases
- Support for multiple database connections
- Schema documentation and relationship mapping
- Error handling with intelligent suggestions

### User Experience
- Real-time chat interface with immediate results
- Query result visualization in tables and charts
- Comprehensive feedback collection system
- Training data recording for model improvement

### ERP R12 Support
- Specialized understanding of ERP organizational structures
- Relationship-aware query building for core ERP tables
- Contextual summarization for business data
- Smart query routing for ERP-specific queries

## 🏗️ System Architecture

Uttoron follows a two-tier client-server architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Client)                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    React + TypeScript                     │  │
│  │  Chat Interface  │  Visualization  │  Feedback System    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP/REST API
┌─────────────────────────────▼───────────────────────────────────┐
│                        Backend (Server)                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                        FastAPI                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   RAG Engine (Core)                       │  │
│  │  Query Routing  │  Schema Retrieval  │  Context Enrichment │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Hybrid Processor                        │  │
│  │  Local Models (Ollama)  │  Cloud Models (OpenRouter)      │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Database Connector                      │  │
│  │  Oracle DB Connection  │  Query Execution  │  Results     │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Vector Store                            │  │
│  │  ChromaDB for schema embeddings and context retrieval     │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Feedback Store                          │  │
│  │  SQLite for storing training data and user feedback       │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interactions
1. User submits natural language query via frontend
2. Frontend sends request to `/chat` endpoint
3. Backend classifies intent using `query_classifier.py`
4. RAG engine retrieves relevant schema context from ChromaDB
5. Hybrid processor routes to local (Ollama) and/or cloud (OpenRouter) LLMs
6. Generated SQL is executed via `db_connector.py`
7. Results returned to frontend for display and visualization
8. User feedback sent to `/feedback` endpoint for training

## 🧰 Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.13)
- **Database:** Oracle (via cx_Oracle), SQLite (for feedback storage)
- **AI/ML Libraries:** Sentence Transformers, ChromaDB, Ollama
- **Vector Store:** ChromaDB
- **External APIs:** OpenRouter (cloud LLMs)
- **Other:** Jinja2, Tenacity, Tabulate, aiohttp

### Frontend
- **Framework:** React + TypeScript
- **Build Tool:** Vite
- **Styling:** Tailwind CSS
- **UI Components:** Lucide React icons, Framer Motion
- **Data Visualization:** Chart.js
- **Markdown Rendering:** React Markdown
- **State Management:** React Context API

### Infrastructure
- **Local Inference:** Ollama
- **Vector Database:** ChromaDB
- **Database Drivers:** cx_Oracle for Oracle connectivity

## 📁 Project Structure

```
uttoron/
├── backend/                           # FastAPI backend application
│   ├── app/                           # Main application code
│   │   ├── SOS/                       # Standard business queries module
│   │   │   ├── __init__.py
│   │   │   ├── query_classifier.py    # Query classification and routing
│   │   │   ├── rag_engine.py          # RAG orchestration for SOS
│   │   │   ├── query_engine.py        # Query execution for SOS
│   │   │   ├── hybrid_processor.py    # Hybrid AI processing for SOS
│   │   │   ├── openrouter_client.py   # OpenRouter API client for SOS
│   │   │   ├── sql_generator.py       # SQL generation for SOS
│   │   │   ├── summarizer.py          # Result summarization for SOS
│   │   │   ├── schema_loader_chroma.py# Schema loading for SOS
│   │   │   ├── vector_store_chroma.py # Vector store integration for SOS
│   │   │   └── query_router.py        # Query routing for SOS
│   │   ├── ERP_R12_Test_DB/           # ERP R12 specific components
│   │   │   ├── __init__.py
│   │   │   ├── query_classifier.py    # ERP-specific query classification
│   │   │   ├── rag_engine.py          # RAG orchestration for ERP
│   │   │   ├── query_engine.py        # Query execution for ERP
│   │   │   ├── hybrid_processor.py    # Hybrid AI processing for ERP
│   │   │   ├── openrouter_client.py   # OpenRouter API client for ERP
│   │   │   ├── sql_generator.py       # SQL generation for ERP
│   │   │   ├── summarizer.py          # Result summarization for ERP
│   │   │   ├── schema_loader_chroma.py# Schema loading for ERP
│   │   │   ├── vector_store_chroma.py # Vector store integration for ERP
│   │   │   ├── query_router.py        # Query routing for ERP
│   │   │   ├── query_interpreter.py   # Query interpretation for ERP
│   │   │   ├── init_erp_r12.py        # ERP schema initialization
│   │   │   └── README.md              # ERP module documentation
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI application and routing
│   │   ├── config.py                  # Application configuration
│   │   ├── db_connector.py            # Database connectivity and execution
│   │   ├── embeddings.py              # Embedding generation
│   │   ├── feedback_store.py          # Feedback storage and management
│   │   ├── hybrid_data_recorder.py    # Training data recording
│   │   ├── llm_client.py              # LLM client abstraction
│   │   ├── ollama_llm.py              # Ollama LLM integration
│   │   ├── sql_generator.py           # Generic SQL generation
│   │   └── vector_store.py            # Generic vector store integration
│   ├── config/                        # Configuration files
│   │   └── sources.json               # Database connection configurations
│   ├── requirements.txt               # Python dependencies
│   ├── start_server.py                # Application entry point
│   ├── debug_config.py                # Debug configuration utilities
│   ├── debug_prompt.py                # Debug prompt utilities
│   ├── setup_db.sql                   # Database setup script
│   ├── setup_training_tables.sql      # Training tables setup script
│   ├── verify_fix.py                  # Fix verification utilities
│   └── verify_fixes.py                # Fix verification scripts
├── frontend/                          # React + TypeScript frontend
│   ├── src/                           # Source code
│   │   ├── components/                # UI components
│   │   │   ├── ChatPanel.tsx          # Main chat interface
│   │   │   ├── MessageBubble.tsx      # Individual message rendering
│   │   │   ├── DataTable.tsx          # Data table component
│   │   │   ├── ChartComponent.tsx     # Data visualization
│   │   │   ├── FeedbackBox.tsx        # Feedback collection
│   │   │   ├── Sidebar.tsx            # Application sidebar
│   │   │   ├── HomePrompts.tsx        # Home prompt suggestions
│   │   │   ├── ChatInput.tsx          # Chat input component
│   │   │   ├── ChatContext.tsx        # Chat state management
│   │   │   ├── DataVisualization.tsx  # Data visualization wrapper
│   │   │   ├── HybridFeedbackBox.tsx  # Hybrid feedback collection
│   │   │   ├── HybridMetadataDisplay.tsx # Hybrid metadata display
│   │   │   ├── PromptSuggestions.tsx  # Prompt suggestions
│   │   │   ├── ThemeContext.tsx       # Theme management
│   │   │   └── ...                    # Other components
│   │   ├── utils/                     # Utility functions
│   │   │   ├── chartUtils.ts          # Chart utilities
│   │   │   ├── exportUtils.ts         # Export utilities
│   │   │   ├── markdown.ts            # Markdown utilities
│   │   │   └── prompts.ts             # Prompt utilities
│   │   ├── App.tsx                    # Main application component
│   │   ├── App.css                    # Application styles
│   │   ├── index.css                  # Global styles
│   │   ├── theme.css                  # Theme styles
│   │   ├── main.tsx                   # Application entry point
│   │   └── vite-env.d.ts              # TypeScript declarations
│   ├── public/                        # Static assets
│   │   ├── Uttoron 1-01.png           # Main logo
│   │   ├── Uttoron Loog-01.png        # Alternative logo
│   │   └── gradient-bg.png            # Background gradient
│   ├── package.json                   # Frontend dependencies
│   ├── tsconfig.json                  # TypeScript configuration
│   ├── tsconfig.app.json              # App TypeScript configuration
│   ├── tsconfig.node.json             # Node TypeScript configuration
│   ├── vite.config.ts                 # Vite configuration
│   ├── tailwind.config.js             # Tailwind CSS configuration
│   └── postcss.config.cjs             # PostCSS configuration
├── common.md                          # Consolidated documentation
└── .gitignore                         # Git ignore file
```

## 🛠️ Installation

### Prerequisites
- Python 3.13
- Node.js 16+ with npm
- Oracle Database access
- Ollama (for local LLM inference)
- ChromaDB (vector store)

### Backend Setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

### Frontend Setup

```bash
cd frontend
npm install
```

## ⚙️ Configuration

### Database Configuration
Update `backend/config/sources.json` with your Oracle database connections:

```json
[
  {
    "id": "source_db_1",
    "type": "oracle",
    "host": "your_oracle_host",
    "port": 1521,
    "service_name": "your_service_name",
    "user": "your_username",
    "password": "your_password"
  },
  {
    "id": "source_db_2",
    "type": "oracle",
    "host": "your_erp_host",
    "port": 1521,
    "service_name": "your_erp_service_name",
    "user": "your_erp_username",
    "password": "your_erp_password"
  }
]
```

### LLM Configuration
Create `backend/.env` with your LLM settings:

```env
# Local models via Ollama
OLLAMA_SQL_URL=http://localhost:11434/api/generate
OLLAMA_SQL_MODEL=deepseek-coder-v2:16b

# Hybrid processing (optional)
HYBRID_ENABLED=true
OPENROUTER_API_KEY=your_api_key_here

# Training data collection
COLLECT_TRAINING_DATA=true
```

## ▶️ Running the Application

### Backend
```bash
cd backend
python start_server.py
```

The backend will be available at **http://localhost:8092**

### Frontend
```bash
cd frontend
npm run dev
```

The frontend will be available at **http://localhost:5173**

## 🚀 Usage

1. Open the web interface at **http://localhost:5173**
2. Type your natural-language query in the chat input
3. View the **generated SQL** and **execution results**
4. Provide **feedback** on the response quality
5. **Visualize** data using the built-in charting capabilities

### Example Queries

#### Standard Business Queries
- "Show me production data for CAL sewing floor 2 from last month"
- "What is the defect rate for Winner production in June 2025?"
- "List all employees in the HR department with their salaries"
- "Find the status of TNA task CTL-25-12345"

#### ERP R12 Queries
- "Show me all operating units"
- "List business groups with their operating units"
- "Find organizations enabled for inventory"
- "What are the legal entities in our ERP system?"

## 📡 API Endpoints

### Core Endpoints
| Method | Path        | Description                       |
|-------:|-------------|-----------------------------------|
| POST   | `/chat`     | Process natural-language queries  |
| POST   | `/feedback` | Submit feedback on responses      |
| GET    | `/health`   | Health check with quality metrics |

### Export Endpoints
| Method | Path               | Description                       |
|-------:|--------------------|-----------------------------------|
| GET    | `/export/sql`      | Export SQL training data as CSV   |
| GET    | `/export/summary`  | Export summary training data as CSV |

### Quality Metrics Endpoints
| Method | Path                               | Description                    |
|-------:|------------------------------------|--------------------------------|
| GET    | `/quality-metrics`                 | Comprehensive quality report   |
| GET    | `/quality-metrics/success-rates`   | Success rate metrics           |
| GET    | `/quality-metrics/user-satisfaction` | User satisfaction metrics    |

## 📊 ERP R12 Support

Uttoron includes specialized support for Oracle ERP R12 with enhanced understanding of ERP organizational structures and relationships.

### ERP R12 Setup

1. **Configure ERP R12 Database Connection**
   Update `backend/config/sources.json` to include the ERP R12 database connection

2. **Initialize ERP R12 Schema**
   ```bash
   cd backend
   python app/ERP_R12_Test_DB/init_erp_r12.py
   ```

### ERP R12 Features

- **Enhanced Entity Recognition** - Specialized understanding of ERP concepts like business groups, operating units, and organizations
- **Relationship-Aware Query Building** - Automatic handling of core ERP relationships between tables
- **Contextual Summarization** - Business-focused summaries of ERP data
- **Smart Query Routing** - Automatic detection and routing of ERP queries

### Core ERP R12 Tables

**HR_OPERATING_UNITS**
- `BUSINESS_GROUP_ID` - Links to business groups
- `ORGANIZATION_ID` - Primary key, links to ORG_ORGANIZATION_DEFINITIONS
- `NAME` - Operating unit name
- `DATE_FROM`/`DATE_TO` - Validity dates
- `USABLE_FLAG` - Usability indicator

**ORG_ORGANIZATION_DEFINITIONS**
- `ORGANIZATION_ID` - Primary key
- `OPERATING_UNIT` - Foreign key to HR_OPERATING_UNITS.ORGANIZATION_ID
- `ORGANIZATION_NAME` - Organization name
- `ORGANIZATION_CODE` - Organization code
- `INVENTORY_ENABLED_FLAG` - Inventory enablement flag

## 🧩 Development

### Backend Development (FastAPI)
Key modules:
- `main.py` — FastAPI application and routing
- `SOS/rag_engine.py` — Core RAG orchestration for standard queries
- `ERP_R12_Test_DB/rag_engine.py` — RAG orchestration for ERP queries
- `db_connector.py` — Database connectivity and schema validation
- `hybrid_processor.py` — Hybrid AI processing logic

### Frontend Development (React + TypeScript)
Key components:
- `App.tsx` — Main application component
- `ChatPanel.tsx` — Main chat interface
- `MessageBubble.tsx` — Individual message rendering
- `DataTable.tsx` — Data table component with visualization
- `ChatContext.tsx` — State management for chat sessions

## ✅ Testing

Run backend tests:
```bash
cd backend
python -m pytest
```

Test ERP components:
```bash
cd backend
python app/ERP_R12_Test_DB/test_erp_r12.py
```

## 🧰 Troubleshooting

### Common Issues
- **Database Connection Errors:** Verify credentials in `backend/config/sources.json`
- **LLM Not Responding:** Check **Ollama** install and pulled models
- **Hybrid Processing Not Working:** Ensure **OPENROUTER_API_KEY** is set and `HYBRID_ENABLED=true`
- **Schema Cache Issues:** Restart the backend to refresh cached schema/embeddings

### Logs
- **Backend:** Terminal where FastAPI server runs
- **Frontend:** Browser **Developer Tools → Console**

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write tests (where applicable)
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.