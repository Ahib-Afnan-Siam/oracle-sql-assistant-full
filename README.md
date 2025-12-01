# Oracle SQL Assistant - Advanced AI Chatbot System
<img width="3497" height="1041" alt="Uttoron 1-01_v2" src="https://github.com/user-attachments/assets/38b0aa9d-fe44-4345-ad41-f84e68a0de81" />

## Overview

The Oracle SQL Assistant is an intelligent AI chatbot that transforms natural language questions into executable SQL queries. This advanced conversational AI system enables users to interact with complex Oracle databases through intuitive chat interfaces, eliminating the need for technical SQL knowledge. The chatbot employs a hybrid AI architecture that intelligently combines local Ollama models with cloud-based OpenRouter APIs to deliver optimal query generation and performance.

## Technology Stack

### Programming Languages
- **Frontend**: TypeScript (primary), JavaScript (supporting)
- **Backend**: Python 3.8+
- **Database**: SQL (Oracle PL/SQL)
- **Configuration**: JSON, Environment Variables

### Frontend Technologies
- **Framework**: React with TypeScript for building the user interface
- **Styling**: Tailwind CSS for responsive design and styling
- **UI Components**: Framer Motion for animations, Lucide React for icons
- **Data Visualization**: Chart.js for creating interactive charts and graphs
- **State Management**: React Context API for application state management
- **Build Tool**: Vite for fast development and production builds
- **Package Management**: npm for dependency management

### Backend Technologies
- **Framework**: FastAPI with Python for high-performance RESTful API services
- **Database Connectivity**: cx_Oracle for Oracle database connections, SQLite for application data
- **AI/ML**: Ollama for local AI model hosting, OpenRouter API for cloud-based models
- **Vector Store**: ChromaDB for schema-aware processing and RAG implementation
- **Authentication**: JWT (JSON Web Tokens) for secure user authentication
- **Environment Management**: python-dotenv for configuration management

### Development Tools
- **IDE**: Visual Studio Code with Python and TypeScript extensions
- **Version Control**: Git for source code management
- **API Testing**: Postman for API endpoint testing
- **Database Tools**: Oracle SQL Developer for database management
- **Containerization**: Docker (optional) for consistent development environments

## Core AI Chatbot Capabilities

- **Conversational SQL Generation**: Transform business questions into optimized SQL queries through natural dialogue with context preservation
- **Hybrid AI Intelligence**: Seamlessly blend local Ollama models with cloud OpenRouter APIs for superior performance and cost optimization
- **Multi-Context Modes**: Four specialized conversation modes for different business needs:
  - **General Mode**: Open-ended queries and general knowledge
  - **SOS Mode**: Emergency response and critical system information
  - **PRAN ERP Mode**: Business intelligence for PRAN enterprise systems
  - **RFL ERP Mode**: Business intelligence for RFL enterprise systems
- **Intelligent Context Management**: Maintain conversation flow with context-aware responses and multi-turn dialogue support
- **Schema-Aware Processing**: Dynamic analysis of database schemas to generate accurate queries
- **Retrieval-Augmented Generation**: Leverage past successful queries and documentation to improve accuracy
- **Direct Database Interaction**: Execute generated SQL queries and display results in user-friendly formats
- **Advanced Data Visualization**: Automatic chart generation for numerical data with performance optimizations
- **Error Interpretation**: Provide clear explanations for database errors and query issues with troubleshooting suggestions
- **Adaptive Learning**: Continuously improve responses through user feedback integration and model fine-tuning

## Authentication

The application uses JWT (JSON Web Tokens) for secure authentication:
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/9e46e422-ba78-48cb-80f8-c5b0e9ed2ee3" />

1. Users log in with username and password
2. On successful authentication, the server generates a JWT token
3. The token is stored in the browser's localStorage
4. For subsequent requests, the token is sent in the Authorization header as a Bearer token
5. The server validates the JWT token to authenticate requests

JWT tokens are stateless and contain user information, eliminating the need for server-side session storage. The system also includes registration functionality and admin privilege management.

## Chatbot User Roles

- **Regular Users**: Full access to AI chatbot functionality across all modes, conversation history, and personal metrics
- **Admin Users**: Enhanced privileges for system management, user oversight, and analytics

## AI Chatbot Setup Instructions

### Project Structure

```
oracle-sql-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application entry point
│   │   ├── dashboard/           # Admin dashboard services
│   │   ├── SOS/                 # SOS mode components
│   │   ├── ERP_R12_Test_DB/     # ERP R12 integration
│   │   ├── hybrid_processor.py  # AI model management
│   │   ├── rag_engine.py        # Retrieval-augmented generation
│   │   └── db_connector.py      # Database connectivity
│   ├── config/
│   │   └── sources.json         # Database configurations
│   ├── requirements.txt         # Python dependencies
│   └── .env                     # Environment variables
└── frontend/
    ├── src/
    │   ├── components/          # React UI components
    │   ├── utils/               # Utility functions
    │   ├── theme/               # Theme configuration
    │   ├── App.tsx             # Main application component
    │   └── main.tsx            # Application entry point
    ├── public/                 # Static assets
    ├── package.json            # Node.js dependencies
    └── vite.config.ts          # Vite configuration
```

### Backend AI Engine Setup

1. Install AI processing dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Configure AI environment variables:
   - Create a `.env` file in the backend directory
   - Set `JWT_SECRET` for secure authentication token signing
   - Set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` for session duration (default: 1440 minutes)
   - Configure database connection strings for PRAN ERP, SOS, and RFL ERP databases
   - Set API keys for OpenRouter and other cloud AI services
   - Configure Oracle database connection parameters for secure data access

3. Launch the AI chatbot backend server:
   ```bash
   python start_server.py
   ```

### Frontend Chat Interface Setup

1. Install chat interface dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Start the chatbot frontend development server:
   ```bash
   npm run dev
   ```

### System Requirements

- Oracle database client libraries for enterprise data connectivity
- Ollama service for local AI model processing
- Node.js and npm for frontend chat interface
- Python 3.8+ for AI backend services

### Development Environment

#### Backend Development
- **IDE**: Visual Studio Code with Python extension
- **Python Version**: 3.8 or higher
- **Virtual Environment**: Recommended for dependency isolation
- **Debugging**: Integrated debugging with VS Code
- **Testing**: pytest for unit and integration tests

#### Frontend Development
- **IDE**: Visual Studio Code with TypeScript and React extensions
- **Node.js Version**: 16 or higher
- **Package Manager**: npm
- **Debugging**: Browser developer tools
- **Testing**: Jest and React Testing Library

#### Database Development
- **Oracle Client**: Oracle Instant Client for database connectivity
- **Database Tools**: Oracle SQL Developer for schema management
- **Monitoring**: Oracle Enterprise Manager for performance tracking

## AI Chatbot API Endpoints
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/9d2936d1-621b-4258-a7ad-18e80e43b3b8" />

### Authentication & User Management
- `POST /login` - User authentication, returns secure JWT token
- `POST /register` - New user registration
- `POST /logout` - Secure user logout (stateless)

### Core Chatbot Functionality
- `POST /chat` - Process natural language queries with intelligent AI response generation
- `GET /chat-history` - Retrieve user's conversation history with the AI chatbot
- `POST /chat-history/restore` - Continue previous conversations with context preservation
- `POST /execute-sql` - Direct execution of stored SQL queries on connected databases
- `POST /chat/feedback` - Submit user feedback to improve AI response quality

### Administrative Functions (requires admin privileges)
- `GET /admin/dashboard/overview` - System performance and usage metrics
- `GET /admin/recent-activity` - Recent chatbot interactions and system events
- `GET /admin/access-requests` - Pending user access approval requests
- `GET /admin/authorized-users` - List of authorized chatbot users
- `GET /admin/user-stats` - User engagement and chatbot usage statistics
- `GET /admin/metrics` - Detailed system performance analytics
- `GET /admin/dashboard/total-chats` - Total chat interactions processed
- `GET /admin/dashboard/token-usage` - AI model token consumption and cost analysis
- `POST /admin/approve-request/{request_id}` - Approve new user access requests
- `POST /admin/deny-request/{request_id}` - Deny user access requests
- `POST /admin/add-user` - Direct user account creation
- `POST /admin/grant-admin-access` - Grant administrative privileges
- `POST /admin/revoke-admin-access` - Revoke administrative privileges
- `POST /admin/enable-user` - Enable user account access
- `POST /admin/disable-user` - Disable user account access
- `DELETE /admin/delete-user/{username}` - Permanently remove user accounts

## AI Chatbot Security Framework

The Oracle SQL Assistant implements comprehensive security measures to protect user data and enterprise systems:

- **JWT Authentication**: All API endpoints (except `/login` and `/register`) require secure JWT token authentication
- **Role-Based Access Control**: Administrative endpoints require both authentication and elevated privileges
- **Password Security**: Passwords are never stored locally (delegated to external HRIS system)
- **CORS Protection**: Configured to allow all origins in development (restrict in production)
- **SQL Injection Prevention**: All database queries use parameterized statements for protection
- **Input Sanitization**: Comprehensive validation and sanitization of all user inputs
- **Credential Protection**: Secure storage of API keys and database credentials
- **Enhanced SQL Validation**: Improved validation logic to accept valid SQL queries while ensuring basic structure
- **Robust SQL Extraction**: Enhanced extraction of SQL from API responses with better handling of various formats
- **Bind Variable Handling**: Proper handling of bind variables in SQL queries with fallback values

## Production Deployment Guidelines

For secure production deployment of the AI chatbot system:

1. Set a strong `JWT_SECRET` environment variable for token security
2. Configure CORS to allow only trusted origins
3. Use a production-grade database for user access management
4. Implement HTTPS for secure token transmission
5. Consider implementing token refresh mechanisms for long-lived sessions
6. Set up proper logging and monitoring for security auditing
7. Configure database connection pooling for optimal performance
8. Implement backup and disaster recovery procedures for data protection

## AI Chatbot Architecture

The Oracle SQL Assistant follows a sophisticated client-server architecture optimized for intelligent query processing:

- **Frontend**: React with TypeScript, Tailwind CSS, and Framer Motion for a responsive chat interface
- **Backend**: FastAPI with Python for high-performance RESTful API services
- **AI Engine**: Hybrid approach combining local Ollama models and cloud OpenRouter APIs
- **Data Storage**: SQLite for application data, Oracle databases for enterprise systems
- **Authentication**: JWT-based stateless authentication for secure sessions

### System Architecture Overview

The Oracle SQL Assistant is built on a modular, scalable architecture designed for enterprise deployment:

```
                    ┌─────────────────┐
                    │   User Browser  │
                    └─────────────────┘
                             │
                    ┌─────────────────┐
                    │  React Frontend │
                    │   (Vite Build)  │
                    └─────────────────┘
                             │
                    ┌─────────────────┐
                    │   FastAPI       │
                    │   Backend       │
                    └─────────────────┘
                    │        │        │
         ┌──────────┘        │        └──────────┐
         │                   │                   │
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Ollama Local   │ │ OpenRouter API  │ │ Oracle/SQLite   │
│     Models      │ │   (Cloud)       │ │   Databases     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Frontend Architecture

The frontend is structured as a modern React application with clear component separation:

- **Component Layer**: Reusable UI components (ChatPanel, MessageBubble, DataTable, etc.)
- **State Management**: React Context for global state (ChatContext, ThemeContext)
- **Routing**: React Router for navigation between different application views
- **API Integration**: Custom hooks and services for backend communication
- **Styling**: Tailwind CSS with custom theme configuration
- **Build System**: Vite for fast development and optimized production builds

### Backend Architecture

The backend follows a modular design pattern with clear separation of concerns:

- **API Layer**: FastAPI routers handling HTTP requests and responses
- **Business Logic Layer**: Core services implementing chatbot functionality
- **AI Processing Layer**: Hybrid processor managing local and cloud AI models
- **Data Access Layer**: Database connectors and query engines
- **RAG Engine**: Retrieval-augmented generation for context-aware processing
- **Authentication Layer**: JWT-based security middleware
- **Dashboard Services**: Analytics and reporting functionality

### Data Flow Architecture

1. **User Interaction**: User submits natural language query through chat interface
2. **Query Processing**: Backend analyzes query intent and context
3. **AI Model Selection**: System selects optimal AI model (local/cloud) based on query complexity
4. **RAG Context Retrieval**: Relevant examples and schema information retrieved from vector store
5. **SQL Generation**: AI models generate SQL based on query and context
6. **Query Validation**: Generated SQL is validated for security and correctness
7. **Database Execution**: Validated SQL executed against target database
8. **Result Processing**: Database results formatted and analyzed
9. **Response Generation**: AI models generate natural language response
10. **Feedback Collection**: User feedback captured for continuous improvement

### AI Model Architecture

The chatbot employs a multi-layered AI approach:

- **Local Models**: Ollama-hosted models for privacy-sensitive processing and offline capabilities
- **Cloud Models**: OpenRouter API access to powerful models like GPT-4 and Claude for complex queries
- **Model Selection**: Intelligent routing based on query complexity, performance requirements, and cost considerations
- **Fallback Mechanisms**: Automatic switching between models in case of failures or timeouts
- **Hybrid Processing**: Parallel processing capabilities with performance monitoring and statistics
- **Enhanced Summarizer Integration**: API-based summarization using cloud models without fixed formats
- **Dynamic Implementation Principles**: No hardcoding of specific query patterns or SQL templates

### Retrieval-Augmented Generation (RAG) Implementation

The chatbot leverages RAG to enhance query understanding and response quality:

- **Context Retrieval**: Relevant examples from previous successful queries are retrieved based on semantic similarity
- **Schema Documentation**: Database schema information and business context are used to guide query generation
- **Feedback Integration**: Positive feedback examples are prioritized in retrieval to improve future responses
- **Dynamic Prompting**: Retrieved context is used to construct more informed prompts for AI models

## Intelligent Chatbot Workflow

1. **Natural Language Input**: Users interact with the chatbot through conversational interfaces, asking questions in plain English
2. **Mode Detection**: System automatically determines the appropriate processing context (General, SOS, PRAN ERP, or RFL ERP) based on user selection or query content
3. **Schema Analysis**: Chatbot analyzes relevant database schema and metadata to understand available tables, columns, and relationships
4. **Retrieval-Augmented Generation (RAG)**: System retrieves relevant context and examples from previous interactions and database documentation to enhance query understanding
5. **Hybrid AI Processing**: Queries are processed by optimal combination of local Ollama models and cloud OpenRouter APIs based on complexity and performance requirements
6. **SQL Generation**: Natural language is converted to optimized, parameterized database queries with proper joins, filters, and aggregations
7. **Query Validation**: Generated SQL is validated for syntax correctness and security compliance before execution
8. **Database Execution**: Validated SQL is executed against appropriate data sources with proper error handling
9. **Result Processing**: Raw database results are analyzed and formatted for optimal presentation
10. **Response Generation**: AI models generate natural language explanations of results, including insights and recommendations
11. **Result Presentation**: Data is formatted in tables, charts, or descriptive responses based on the nature of the information
12. **Feedback Integration**: User feedback (thumbs up/down and comments) is collected to improve future AI responses and model performance

### Query Processing Pipeline

The AI chatbot employs a sophisticated multi-stage query processing pipeline:

- **Intent Recognition**: Natural language queries are analyzed to determine user intent and required data entities
- **Entity Extraction**: Key business terms, dates, metrics, and filters are identified and classified
- **Context Integration**: Previous conversation context is incorporated to maintain dialogue coherence
- **Schema Mapping**: Extracted entities are mapped to appropriate database tables and columns
- **Query Construction**: SQL statements are built with proper joins, aggregations, and filtering
- **Performance Optimization**: Queries are optimized for execution speed and resource usage
- **Security Validation**: All queries undergo security checks to prevent injection attacks
- **Execution Planning**: Optimal execution strategies are determined based on data volume and complexity

### Query Optimization Techniques

The chatbot implements advanced query optimization to ensure efficient database interactions:

- **Index Awareness**: Queries are constructed to leverage existing database indexes for faster execution
- **Join Optimization**: Intelligent selection of join types and order based on table sizes and relationships
- **Filter Pushdown**: Early application of filters to reduce data processing requirements
- **Aggregation Planning**: Efficient grouping and aggregation strategies to minimize computational overhead
- **Subquery Optimization**: Conversion of complex nested queries to more efficient join operations
- **Resource Limiting**: Automatic application of limits and pagination for large result sets
- **Execution Plan Analysis**: Real-time monitoring of query performance with adaptive optimization

## Core Chatbot Components

### Frontend Chat Interface
- **Responsive Design**: Mobile-first design with adaptive layouts for all device sizes
- **Theme System**: Dark/light theme switching with CSS variables for consistent styling
- **Interactive Chat**: Real-time messaging interface with typing indicators and message animations
- **Message Types**: Support for various message formats including text, tables, charts, and error explanations
- **File Attachments**: Drag-and-drop file upload support for contextual data sharing
- **Data Visualization**: Dynamic chart generation (bar, line, pie, doughnut) with Chart.js
- **Export Capabilities**: One-click export of results to CSV, Excel, PDF, and image formats
- **Feedback System**: Integrated thumbs-up/down feedback and detailed comment collection
- **Performance Optimizations**: Virtual scrolling and data sampling for large dataset handling
- **Chat History**: Persistent conversation storage with restore functionality

### Backend AI Engine
- **FastAPI RESTful API**: High-performance asynchronous API with automatic documentation
- **Hybrid AI Processing**: Intelligent model selection between local Ollama and cloud OpenRouter APIs
- **Database Connectivity**: Secure, pooled connections to multiple Oracle databases with retry logic
- **Schema Management**: Dynamic schema analysis and metadata caching for query optimization
- **Retrieval-Augmented Generation**: Context retrieval from previous interactions and documentation
- **Query Optimization**: SQL generation with performance considerations and best practices
- **Security Framework**: JWT authentication, parameterized queries, and input sanitization
- **Session Management**: Stateful conversation context tracking across multiple interactions
- **Error Handling**: Comprehensive exception handling with user-friendly error messages
- **Logging & Monitoring**: Structured logging with performance metrics and usage analytics
- **Token Management**: Cost tracking and optimization for cloud API usage
- **Feedback Processing**: Automated analysis of user feedback for continuous model improvement
- **Token Usage Recording**: Comprehensive implementation for both SOS and ERP systems with real-time data recording
- **Database Query Enhancement**: Support for technical database administration queries in SOS backend system

### Response Generation Process

The chatbot employs a multi-stage response generation process to ensure accurate and helpful outputs:

- **Result Analysis**: Database results are analyzed to identify key metrics, trends, and anomalies
- **Data Formatting**: Results are formatted appropriately (tabular, chart, or text) based on data characteristics
- **Natural Language Generation**: AI models convert structured data into conversational explanations
- **Insight Extraction**: Key business insights and recommendations are identified from the data
- **Contextualization**: Responses are tailored to the user's role, mode, and conversation history
- **Confidence Scoring**: Each response is evaluated for accuracy and reliability
- **Error Handling**: Graceful handling of edge cases and ambiguous queries with helpful suggestions

### Query History System

The system implements a comprehensive query history system for tracking user interactions:

- **Unified Storage**: All query-related information stored in dashboard_query_history table
- **Execution Tracking**: Monitors query execution status, time, and row counts
- **Feedback Integration**: Built-in system for collecting user feedback on responses
- **Dashboard Integration**: Fully integrated with admin dashboard for analytics and monitoring
- **Referential Integrity**: Foreign key constraints link user activities to user_access_list table for data consistency

## Multi-Database Integration

The AI chatbot seamlessly connects to multiple specialized databases:

1. **Application Database** (SQLite): User accounts, conversation history, feedback data
2. **PRAN ERP Database** (Oracle): Business intelligence data for PRAN operations
3. **SOS Database** (Oracle): Emergency response and critical system information
4. **RFL ERP Database** (Oracle): Business intelligence data for RFL operations

### Database Schema Handling

The chatbot implements sophisticated schema management to ensure accurate query generation:

- **Dynamic Schema Discovery**: Automatic detection of tables, columns, relationships, and constraints
- **Schema Caching**: In-memory caching of schema information for improved performance
- **Business Context Mapping**: Association of technical schema elements with business terminology
- **Schema Evolution**: Adaptive handling of schema changes without requiring system restarts
- **Cross-Database Queries**: Intelligent handling of queries that span multiple database systems
- **Metadata Enrichment**: Enhancement of raw schema information with business context and usage patterns

### ERP R12 Support

Specialized support for Oracle ERP R12 databases with enhanced understanding of ERP organizational structures:

- **Enhanced Entity Recognition**: Specialized understanding of ERP concepts like business groups, operating units, and organizations
- **Relationship-Aware Query Building**: Automatic handling of core ERP relationships between tables
- **Contextual Summarization**: Business-focused summaries of ERP data
- **Smart Query Routing**: Automatic detection and routing of ERP queries
- **Schema Documentation**: Comprehensive documentation of ERP R12 tables and columns

### Database Query Solutions

Advanced capabilities for handling technical database queries:

- **Dynamic Query Classification**: Recognition of database-related queries through pattern matching
- **System Table Awareness**: Understanding of Oracle system tables (USER_OBJECTS, DBA_USERS, V$SESSION, etc.)
- **Schema Context Guidance**: AI models receive context about system tables without hardcoded templates
- **Flexible Intent Classification**: Classification based on general categories rather than specific patterns
- **No Hardcoding Principle**: All implementations are fully dynamic and AI-driven without fixed templates

## Chatbot Analytics & Monitoring
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/1426bd60-6af4-4516-8ae5-ee8452691eb6" />

- Real-time conversation metrics and user engagement tracking
- AI model token usage monitoring and cost analysis
- User activity patterns and chatbot utilization analytics
- System performance monitoring and optimization insights
- Error tracking and resolution reporting for continuous improvement
- Actual data verification from DASHBOARD_CHATS and DASHBOARD_TOKEN_USAGE tables
- Database query enhancement for SOS backend system with support for technical database queries
- Token usage dashboard with real-time insights on token consumption

## Continuous Learning & Improvement

The Oracle SQL Assistant implements a comprehensive feedback loop to continuously enhance its performance:

- **User Feedback Collection**: Integrated thumbs-up/down ratings and comment submission for all AI responses
- **Feedback Analysis**: Automated analysis of feedback patterns to identify common issues and improvement areas
- **Model Retraining**: Periodic fine-tuning of AI models based on successful query patterns and feedback
- **Performance Metrics**: Continuous monitoring of response accuracy, query success rates, and user satisfaction
- **A/B Testing**: Capability to test new models and approaches with subsets of users
- **Knowledge Base Updates**: Regular updates to the RAG context database with successful query examples
- **Error Pattern Recognition**: Automated identification and resolution of common error scenarios
- **Feature Enhancement**: Data-driven development of new capabilities based on user needs and usage patterns
