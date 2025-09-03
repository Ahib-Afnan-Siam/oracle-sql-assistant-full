# Oracle SQL Assistant

> A sophisticated natural-language-to-SQL system that lets users query **Oracle databases** with conversational input. It pairs advanced AI processing with a user-friendly interface to **generate, execute, and visualize** Oracle SQL from plain English.

---

## 📑 Table of Contents
- [Overview](#overview)
- [✨ Features](#-features)
  - [Core Functionality](#core-functionality)
  - [Advanced AI Capabilities](#advanced-ai-capabilities)
  - [Training & Feedback System](#training--feedback-system)

---

## Overview
This application converts English queries into **executable Oracle SQL**, runs them directly against your Oracle databases, and presents results in **tables or charts**—with rich error handling and schema-aware reasoning.

---

## ✨ Features

### Core Functionality
- **Natural Language to SQL** — Convert English queries into executable Oracle SQL.
- **Schema-Aware Processing** — Uses vector embeddings to understand database schema context.
- **Direct Database Execution** — Execute generated SQL directly against Oracle databases.
- **Error Handling & Suggestions** — Helpful error messages with next-step query suggestions.
- **Query Result Visualization** — Display data in tables or charts.

### Advanced AI Capabilities
- **Hybrid AI Processing** — Combines local LLMs with cloud models for optimal responses.
- **Dynamic Entity Recognition** — Detects companies, floors, dates, and CTL codes in queries.
- **Intent Classification** — Routes queries through specialized processing paths.
- **Confidence Scoring** — Rates the reliability of generated SQL.
- **Model Selection** — Automatically chooses the best processing approach based on query complexity.

### Training & Feedback System
- **Comprehensive Feedback Collection** — Gather user feedback on AI responses.
- **Training Data Recording** — Store query context, responses, and performance metrics.
- **Quality Metrics Analysis** — Monitor success rates and user satisfaction.
- **Continuous Improvement** — Use feedback data to enhance model performance.

## 🏗️ Architecture

```text
oracle-sql-assistant/
├── backend/                     # FastAPI backend application
│   ├── app/                     # Main application code
│   │   ├── rag_engine.py        # RAG orchestration and query processing
│   │   ├── hybrid_processor.py  # Hybrid AI processing system
│   │   ├── query_classifier.py  # Query classification and routing
│   │   ├── db_connector.py      # Database connections and schema validation
│   │   └── ...                  # Other components
│   ├── config/                  # Configuration files
│   └── requirements.txt         # Python dependencies
└── frontend/                    # React/TypeScript frontend
    ├── src/                     # Source code
    │   ├── components/          # UI components
    │   └── utils/               # Utility functions
    └── package.json             # Frontend dependencies


## 🧰 Technology Stack

### Backend
- **Framework:** FastAPI  
- **Database:** Oracle (via `cx_Oracle`), SQLite (for feedback storage)  
- **AI/ML:** Sentence Transformers, ChromaDB, Ollama  
- **Vector Store:** ChromaDB  
- **External APIs:** OpenRouter (cloud LLMs)

### Frontend
- **Framework:** React + TypeScript  
- **Styling:** Tailwind CSS  
- **UI Components:** Lucide React icons, Framer Motion  
- **Data Visualization:** Chart.js  
- **Markdown Rendering:** React Markdown

### Prerequisites
- **Python:** 3.13  
- **Node.js:** 16+ and npm  
- **Database:** Oracle access  
- **Local Inference:** Ollama  
- **Vector DB:** ChromaDB

## 🛠️ Installation

### Backend Setup

**1) Navigate to the backend directory**
```bash
cd backend
```

**2) Create a virtual environment**
```bash
python -m venv venv
```

**3) Activate the virtual environment**
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

**4) Install Python dependencies**
```bash
pip install -r requirements.txt
```

**5) Create a `.env` file (in `backend/`)**
```env
# ── Oracle Database Configuration ───────────────────────────────────────────────
VECTOR_DB_HOST=your_vector_db_host
VECTOR_DB_PORT=1521
VECTOR_DB_SERVICE=your_service_name
VECTOR_DB_USER=your_username
VECTOR_DB_PASSWORD=your_password

# ── LLM Configuration (Local via Ollama) ───────────────────────────────────────
# Default Ollama HTTP endpoint
OLLAMA_SQL_URL=http://localhost:11434/api/generate
# SQL-focused local model
OLLAMA_SQL_MODEL=deepseek-coder-v2:16b
# Reasoning/summary model (optional)
OLLAMA_R1_MODEL=deepseek-r1:14b

# ── Hybrid Processing (Optional: Cloud via OpenRouter) ─────────────────────────
HYBRID_ENABLED=true           # set to false to use local-only
OPENROUTER_API_KEY=your_api_key_here

# ── Training Data Collection ───────────────────────────────────────────────────
COLLECT_TRAINING_DATA=true
```

---

### Frontend Setup

**1) Navigate to the frontend directory**
```bash
cd frontend
```

**2) Install dependencies**
```bash
npm install
```

**(Optional) Start the dev server**
```bash
npm run dev
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
  }
]
```

### LLM Configuration
Configure your LLM settings in the `.env` file (see Installation section):
- **Local models** via **Ollama**
- **Cloud models** via **OpenRouter API**
- **Hybrid processing** (combine both)

#### Enable Hybrid Processing
```env
HYBRID_ENABLED=true
OPENROUTER_API_KEY=your_openrouter_api_key
```

---

## ▶️ Running the Application

### Backend
Start the FastAPI server:
```bash
cd backend
uvicorn app.main:app --port 8090 --reload
```
The backend will be available at **http://localhost:8090**

### Frontend
Start the React development server:
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

### 🧪 Example Queries
- “Show me production data for **CAL sewing floor 2** from **last month**”
- “What is the **defect rate** for **Winner** production in **June 2025**?”
- “List all **employees** in the **HR** department with their **salaries**”
- “Find the status of **TNA** task **CTL-25-12345**”

---

## 🧠 Advanced Features

### Hybrid AI Processing
The system uses both local and cloud-based LLMs:
- **Local Processing:** Fast, private, runs without internet (limited capacity)
- **Cloud Processing:** More powerful; requires internet access
- **Parallel Processing:** Local and cloud models run simultaneously
- **Intelligent Selection:** Automatically chooses the best response using confidence scores

### Training Data Collection
When enabled, the system collects comprehensive training signals:
- Query context and classification
- Model responses and performance metrics
- User feedback and satisfaction scores
- API usage and cost tracking

### Quality Metrics
Monitor system performance through:
- Query understanding accuracy
- SQL execution success rates
- User satisfaction indicators
- Business logic compliance
- Response time analysis

---

## 📡 API Endpoints

### Core Endpoints
| Method | Path         | Description                         |
|-------:|--------------|-------------------------------------|
| POST   | `/chat`      | Process natural-language queries    |
| POST   | `/feedback`  | Submit feedback on responses        |
| GET    | `/health`    | Health check with quality metrics   |

### Export Endpoints
| Method | Path              | Description                        |
|-------:|-------------------|------------------------------------|
| GET    | `/export/sql`     | Export SQL training data as CSV    |
| GET    | `/export/summary` | Export summary training data as CSV|

### Quality Metrics Endpoints
| Method | Path                              | Description                   |
|-------:|-----------------------------------|-------------------------------|
| GET    | `/quality-metrics`                | Comprehensive quality report  |
| GET    | `/quality-metrics/success-rates`  | Success rate metrics          |
| GET    | `/quality-metrics/user-satisfaction` | User satisfaction metrics  |

---

## 🧩 Development

### Backend Development (FastAPI)
- `main.py` — FastAPI application and routing  
- `rag_engine.py` — Core RAG orchestration  
- `hybrid_processor.py` — Hybrid AI processing logic  
- `query_classifier.py` — Query classification and routing  
- `db_connector.py` — Database connectivity and schema validation  

### Frontend Development (React + TypeScript)
- `App.tsx` — Main application component  
- `ChatContext.tsx` — State management for chat sessions  
- `ChatPanel.tsx` — Main chat interface  
- `MessageBubble.tsx` — Individual message rendering  
- `DataTable.tsx` — Data table component with visualization  

---

## ✅ Testing

Run backend tests:
```bash
cd backend
python -m pytest
```

---

## 🧰 Troubleshooting

### Common Issues
- **Database Connection Errors:** Verify credentials in `backend/config/sources.json`
- **LLM Not Responding:** Check **Ollama** installation and that required models are pulled
- **Hybrid Processing Not Working:** Ensure **OPENROUTER_API_KEY** is set and `HYBRID_ENABLED=true`
- **Schema Cache Issues:** Restart the backend to refresh cached schema/embeddings

### Logs
- **Backend:** Shown in the terminal where the FastAPI server runs  
- **Frontend:** Open browser **Developer Tools → Console**

---

## 🤝 Contributing

1. Fork the repository  
2. Create a feature branch  
3. Make your changes  
4. Write tests (where applicable)  
5. Submit a pull request  

---

## 📄 License
This project is licensed under the **MIT License** — see the `LICENSE` file for details.

---

## 🆘 Support
For issues and feature requests, please open a **GitHub Issue** or contact the development team.
