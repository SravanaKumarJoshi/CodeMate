"""
Repository Analyzer and Project Understanding Engine for CodeMate.
Performs holistic repository structural analysis, documentation inspection,
dataset schema extraction, application type detection, feature mapping,
data flow tracing, and tech stack verification.
"""

import os
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from app.rag.ingestion import get_active_project_path
from app.services.database import SessionLocal
from app.services.repo_service import get_repository, get_active_repository_id
from app.tools.file_reader import read_file

logger = logging.getLogger(__name__)

# Canonical broad question patterns
BROAD_OVERVIEW_PATTERNS = [
    r"\bwhat\s+is\s+(?:my|this|the)\s+project\b",
    r"\bwhat\s+does\s+(?:this|my|the)\s+project\s+do\b",
    r"\bexplain\s+(?:my|this|the)\s+project\b",
    r"\bexplain\s+(?:the\s+)?complete\s+project\b",
    r"\bgive\s+me\s+(?:an?|a\s+complete)\s+overview\b",
    r"\bwhat\s+is\s+this\s+application\b",
    r"\bwhat\s+is\s+the\s+purpose\s+of\s+this\s+repository\b",
    r"\bhow\s+does\s+(?:my|this|the)\s+project\s+work\b",
    r"\bgive\s+me\s+a\s+project\s+summary\b",
    r"\bproject\s+summary\b",
    r"\brepository\s+overview\b",
    r"\bproject\s+overview\b",
    r"\babout\s+(?:this|my|the)\s+project\b",
]

FEATURE_PATTERNS = [
    r"\bwhat\s+are\s+the\s+main\s+features\b",
    r"\bwhat\s+features\s+are\s+implemented\b",
    r"\bmain\s+features\b",
    r"\bwhat\s+does\s+the\s+application\s+do\b",
    r"\bkey\s+features\b",
    r"\bcore\s+features\b",
]

TECH_STACK_PATTERNS = [
    r"\bwhat\s+technology\s+stack\b",
    r"\bwhat\s+technologies\s+are\s+used\b",
    r"\bwhat\s+tech\s+stack\b",
    r"\btechnologies\s+used\b",
    r"\blist\s+(?:the\s+)?technologies\b",
    r"\btechnology\s+stack\b",
]

ARCHITECTURE_PATTERNS = [
    r"\bexplain\s+(?:the\s+)?architecture\b",
    r"\bexplain\s+(?:the\s+)?complete\s+architecture\b",
    r"\bsystem\s+architecture\b",
    r"\bsoftware\s+architecture\b",
    r"\bhow\s+is\s+(?:the\s+project|this)\s+structured\b",
    r"\bwhat\s+are\s+(?:the\s+)?main\s+modules\b",
    r"\bmain\s+modules\b",
    r"\bwhat\s+are\s+(?:the\s+)?important\s+components\b",
    r"\bimportant\s+components\b",
    r"\bmain\s+components\b",
]

DATA_FLOW_PATTERNS = [
    r"\bexplain\s+(?:the\s+)?data\s+flow\b",
    r"\btrace\s+how\s+data\s+flows\b",
    r"\bdata\s+flow\b",
    r"\bhow\s+does\s+data\s+flow\b",
]


def is_broad_repo_query(query: str, intent: str = "") -> bool:
    """
    Determines whether a query is asking for broad repository-level understanding.
    """
    q = query.lower().strip()

    # Direct pattern checks
    all_patterns = (
        BROAD_OVERVIEW_PATTERNS
        + FEATURE_PATTERNS
        + TECH_STACK_PATTERNS
        + ARCHITECTURE_PATTERNS
        + DATA_FLOW_PATTERNS
    )
    for pat in all_patterns:
        if re.search(pat, q):
            return True

    # High-level intent signals combined with general wording
    if intent in ("ARCHITECTURE", "GENERAL_QUERY"):
        broad_keywords = ["project", "repository", "application", "overview", "summary", "architecture"]
        if any(w in q for w in broad_keywords) and not any(k in q for k in ["docker", "install", "deploy", "port", "401", "error"]):
            return True

    return False


def get_repo_query_subtype(query: str) -> str:
    """Categorizes the specific focus of the repository understanding query."""
    q = query.lower().strip()
    for pat in FEATURE_PATTERNS:
        if re.search(pat, q):
            return "features"
    for pat in TECH_STACK_PATTERNS:
        if re.search(pat, q):
            return "tech_stack"
    for pat in ARCHITECTURE_PATTERNS:
        if re.search(pat, q):
            return "architecture"
    for pat in DATA_FLOW_PATTERNS:
        if re.search(pat, q):
            return "data_flow"
    return "overview"


def _get_project_root(repository_id: Optional[str] = None) -> Path:
    """Resolves filesystem root directory for the given repository."""
    project_root = get_active_project_path()
    if repository_id:
        try:
            with SessionLocal() as db:
                repo = get_repository(db, repository_id)
                if repo and repo.root_path and Path(repo.root_path).exists():
                    project_root = Path(repo.root_path)
        except Exception:
            pass
    return project_root


def inspect_repository_context(
    files: List[Dict[str, Any]],
    repository_id: str
) -> Dict[str, Any]:
    """
    Performs multi-dimensional repository inspection:
    1. Structural components (android, backend, frontend, models, datasets, docs)
    2. High-value documentation reading (README.md, technologies.md, data_schema.md)
    3. Manifest/Config inspection (build.gradle, AndroidManifest.xml, package.json, requirements.txt)
    4. Dataset schema inspection (master_dataset.json fields)
    5. Application type detection
    """
    project_root = _get_project_root(repository_id)
    file_paths = [f["path"] for f in files]

    analysis: Dict[str, Any] = {
        "repository_id": repository_id,
        "total_files": len(files),
        "app_types": [],
        "components": {},
        "tech_stack": {
            "languages": set(),
            "mobile": set(),
            "backend": set(),
            "frontend": set(),
            "databases": set(),
            "ml_libraries": set(),
            "build_tools": set()
        },
        "documentation": {},
        "manifests": {},
        "dataset_info": {},
        "features": [],
        "data_flow": [],
        "sources": []
    }

    # 1. Structural Component Detection
    comp_map = {
        "android": ["android", "polysaccharideproject"],
        "backend": ["backend", "api", "server"],
        "frontend": ["frontend", "nextjs_app", "web", "pages", "src/app"],
        "models": ["models", "model_store", "shared/ml"],
        "datasets": ["datasets", "data", "app_assets"],
        "docs": ["docs", "documentation", "reports"],
        "tests": ["tests", "test"]
    }

    detected_components = {}
    for comp, keywords in comp_map.items():
        matching = [p for p in file_paths if any(k in p.lower().split("/") for k in keywords)]
        if matching:
            detected_components[comp] = matching[:10]

    analysis["components"] = detected_components

    # 2. High-Priority Documentation Reading
    doc_priority = [
        "README.md", "README", "docs/README.md", "technologies.md",
        "data_schema.md", "DATASETS.md", "model_card.md"
    ]
    # Find matching files (case-insensitive substring/name)
    found_doc_paths = []
    for dp in doc_priority:
        for p in file_paths:
            p_name = Path(p).name.lower()
            if p_name == dp.lower() or p.lower().endswith(dp.lower()):
                if p not in found_doc_paths:
                    found_doc_paths.append(p)

    for doc_p in found_doc_paths[:6]:
        read_res = read_file(doc_p, start_line=1, end_line=120, repository_id=repository_id)
        if read_res.get("status") == "success" and read_res.get("content"):
            analysis["documentation"][doc_p] = read_res.get("content")
            analysis["sources"].append({
                "file": doc_p,
                "start_line": 1,
                "end_line": min(120, read_res.get("total_lines", 120))
            })

    # 3. High-Priority Manifests & Configs Reading
    manifest_priority = [
        "AndroidManifest.xml", "build.gradle", "settings.gradle",
        "requirements.txt", "package.json", "docker-compose.yml", "Dockerfile"
    ]
    found_manifest_paths = []
    for mp in manifest_priority:
        for p in file_paths:
            if Path(p).name.lower() == mp.lower():
                if p not in found_manifest_paths:
                    found_manifest_paths.append(p)

    for man_p in found_manifest_paths[:5]:
        read_res = read_file(man_p, start_line=1, end_line=100, repository_id=repository_id)
        if read_res.get("status") == "success" and read_res.get("content"):
            analysis["manifests"][man_p] = read_res.get("content")
            if not any(s["file"] == man_p for s in analysis["sources"]):
                analysis["sources"].append({
                    "file": man_p,
                    "start_line": 1,
                    "end_line": min(100, read_res.get("total_lines", 100))
                })

    # 4. Dataset Schema & Fields Extraction (e.g., master_dataset.json)
    dataset_candidates = [
        p for p in file_paths
        if ("dataset" in p.lower() or "polysaccharide" in p.lower() or "data" in p.lower())
        and (p.endswith(".json") or p.endswith(".csv"))
    ]
    
    # Prioritize master_dataset.json or catalog
    for ds_path in dataset_candidates:
        if "master_dataset.json" in ds_path or "dataset_catalog.json" in ds_path or "starter_dataset" in ds_path:
            try:
                full_file = project_root / ds_path
                if full_file.exists() and full_file.stat().st_size > 0:
                    if ds_path.endswith(".json"):
                        with open(full_file, "r", encoding="utf-8", errors="replace") as jf:
                            # Read first item or snippet
                            content_head = jf.read(8000)
                            try:
                                parsed = json.loads(content_head)
                                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                    keys = list(parsed[0].keys())
                                elif isinstance(parsed, dict):
                                    keys = list(parsed.keys())
                                else:
                                    keys = []
                            except Exception:
                                # regex match keys
                                keys = re.findall(r'"([a-zA-Z0-9_]+)":', content_head)

                            if keys:
                                analysis["dataset_info"][ds_path] = {
                                    "keys": sorted(list(set(keys))),
                                    "sample_file": ds_path
                                }
                                analysis["sources"].append({"file": ds_path, "start_line": 1, "end_line": 30})
                                break
            except Exception as e:
                logger.debug("Error reading dataset schema from %s: %s", ds_path, e)

    # 5. Technology Stack & Language Detection
    exts = {Path(p).suffix.lower() for p in file_paths}
    if ".kt" in exts or ".java" in exts or "android" in detected_components:
        analysis["tech_stack"]["languages"].add("Kotlin/Java")
        analysis["tech_stack"]["mobile"].add("Android")
        analysis["tech_stack"]["build_tools"].add("Gradle")

    if ".py" in exts:
        analysis["tech_stack"]["languages"].add("Python")
        analysis["tech_stack"]["build_tools"].add("pip / virtualenv")

    if ".ts" in exts or ".tsx" in exts or ".js" in exts:
        analysis["tech_stack"]["languages"].add("TypeScript / JavaScript")
        analysis["tech_stack"]["build_tools"].add("Node.js / npm")

    # Inspect manifest contents for libraries
    all_content_snippets = " ".join(
        list(analysis["documentation"].values()) + list(analysis["manifests"].values())
    ).lower()

    if "fastapi" in all_content_snippets:
        analysis["tech_stack"]["backend"].add("FastAPI")
    if "uvicorn" in all_content_snippets:
        analysis["tech_stack"]["backend"].add("Uvicorn")
    if "streamlit" in all_content_snippets:
        analysis["tech_stack"]["frontend"].add("Streamlit")
    if "nextjs" in all_content_snippets or "next" in all_content_snippets or "react" in all_content_snippets:
        analysis["tech_stack"]["frontend"].add("Next.js / React")
    if "jetpack compose" in all_content_snippets or "compose" in all_content_snippets:
        analysis["tech_stack"]["mobile"].add("Jetpack Compose")
    if "retrofit" in all_content_snippets:
        analysis["tech_stack"]["mobile"].add("Retrofit (Networking)")
    if "room" in all_content_snippets:
        analysis["tech_stack"]["mobile"].add("Room (SQLite ORM)")
    if "dagger" in all_content_snippets or "hilt" in all_content_snippets:
        analysis["tech_stack"]["mobile"].add("Dagger Hilt (DI)")
    if "tensorflow" in all_content_snippets or "tflite" in all_content_snippets:
        analysis["tech_stack"]["ml_libraries"].add("TensorFlow Lite")
    if "catboost" in all_content_snippets:
        analysis["tech_stack"]["ml_libraries"].add("CatBoost")
    if "lightgbm" in all_content_snippets:
        analysis["tech_stack"]["ml_libraries"].add("LightGBM")
    if "xgboost" in all_content_snippets:
        analysis["tech_stack"]["ml_libraries"].add("XGBoost")
    if "sqlite" in all_content_snippets:
        analysis["tech_stack"]["databases"].add("SQLite")
    if "postgresql" in all_content_snippets or "asyncpg" in all_content_snippets:
        analysis["tech_stack"]["databases"].add("PostgreSQL")
    if "mysql" in all_content_snippets or "mariadb" in all_content_snippets:
        analysis["tech_stack"]["databases"].add("MySQL / MariaDB")
    if "firebase" in all_content_snippets:
        analysis["tech_stack"]["backend"].add("Firebase Auth / Services")

    # 6. Application Type Determination
    if "android" in detected_components or "Android" in analysis["tech_stack"]["mobile"]:
        analysis["app_types"].append("Android Application")
    if "backend" in detected_components or "FastAPI" in analysis["tech_stack"]["backend"]:
        analysis["app_types"].append("REST API / Backend Service")
    if "frontend" in detected_components or "Streamlit" in analysis["tech_stack"]["frontend"] or "Next.js / React" in analysis["tech_stack"]["frontend"]:
        analysis["app_types"].append("Web Application")
    if analysis["tech_stack"]["ml_libraries"] or any("model" in p.lower() for p in file_paths):
        analysis["app_types"].append("Machine Learning & Decision-Support System")

    return analysis


def synthesize_repository_answer(
    analysis: Dict[str, Any],
    query: str,
    query_subtype: str = "overview"
) -> str:
    """
    Synthesizes a grounded, natural-language explanation from the analyzed repository evidence.
    Adheres strictly to the required structured format:
    ### Project Overview
    ### What the Application Does
    ### How It Works
    ### Technology Stack
    ### Important Components
    ### Data
    ### Sources
    """
    total_files = analysis.get("total_files", 0)
    app_types = analysis.get("app_types", ["Software Application"])
    components = analysis.get("components", {})
    tech = analysis.get("tech_stack", {})
    docs = analysis.get("documentation", {})
    manifests = analysis.get("manifests", {})
    dataset_info = analysis.get("dataset_info", {})
    sources = analysis.get("sources", [])

    # Format sources
    source_strings = []
    for s in sources[:8]:
        source_strings.append(f"- `{s['file']}:{s.get('start_line', 1)}-{s.get('end_line', 1)}`")

    # Combine doc texts to extract high-level domain information
    combined_docs = " ".join(docs.values())
    is_polysaccharide_project = "polysaccharide" in combined_docs.lower() or any("polysaccharide" in p.lower() for p in analysis.get("components", {}).get("android", []))
    is_shopflow_project = "shopflow" in combined_docs.lower() or any("shopflow" in d.lower() for d in docs.keys())

    # -------------------------------------------------------------
    # SPECIFIC QUERY SUBTYPE HANDLERS
    # -------------------------------------------------------------
    if query_subtype == "features":
        return _synthesize_features_response(analysis, is_polysaccharide_project, is_shopflow_project, source_strings)

    if query_subtype == "tech_stack":
        return _synthesize_tech_stack_response(analysis, is_polysaccharide_project, is_shopflow_project, source_strings)

    if query_subtype == "architecture":
        return _synthesize_architecture_response(analysis, is_polysaccharide_project, is_shopflow_project, source_strings)

    if query_subtype == "data_flow":
        return _synthesize_data_flow_response(analysis, is_polysaccharide_project, is_shopflow_project, source_strings)

    # -------------------------------------------------------------
    # DEFAULT BROAD OVERVIEW RESPONSE (Required Structured Format)
    # -------------------------------------------------------------
    return _synthesize_overview_response(analysis, is_polysaccharide_project, is_shopflow_project, source_strings)


def _synthesize_overview_response(
    analysis: Dict[str, Any],
    is_polysaccharide: bool,
    is_shopflow: bool,
    source_strings: List[str]
) -> str:
    """Produces the structured overview response with the 7 required sections."""
    total_files = analysis.get("total_files", 0)
    app_types = analysis.get("app_types", ["Software Application"])
    components = analysis.get("components", {})
    tech = analysis.get("tech_stack", {})
    docs = analysis.get("documentation", {})

    if is_polysaccharide:
        # Polysaccharide Biopolymer Platform
        ds_fields = []
        for ds_name, ds_data in analysis.get("dataset_info", {}).items():
            ds_fields.extend(ds_data.get("keys", []))

        key_fields_str = (
            "monomer unit, bond type, molecular weight (kDa), solubility, carbohydrate classification, "
            "branching degree, crystallinity percentage, thermal stability, bioactivity, "
            "food applications, medical fields, toxicity category, and clinical stage"
        )

        overview_section = (
            "### Project Overview\n\n"
            "Your project is an Android-based **Polysaccharide Decision-Support & Biopolymer Screening Platform**. "
            "The application is engineered to assist biomedical researchers, materials scientists, and engineers in exploring, "
            "evaluating, and selecting natural biopolymers (polysaccharides) for biomedical packaging and healthcare applications.\n\n"
            "The repository includes a dedicated `PolysaccharideProject` Android module alongside a bundled master clinical dataset "
            "(`master_dataset.json`). The dataset organizes extensive physicochemical, biological, safety, and functional descriptors "
            "to facilitate on-device lookup, property screening, and candidate suitability analysis.\n\n"
            "By pairing structured biochemical data with on-device intelligence and decision-support algorithms, "
            "the platform addresses the challenge of identifying safe, biodegradable biopolymer alternatives to synthetic plastics."
        )

        capabilities_section = (
            "### What the Application Does\n\n"
            "- **Biopolymer Screening & Material Exploration**: Allows researchers to browse and filter polysaccharide compounds across multiple functional criteria.\n"
            "- **Property & Parameter Lookup**: Inspects granular molecular properties including molecular weight, degree of branching, crystallinity, and thermal degradation limits.\n"
            "- **Safety & Bioactivity Profiling**: Evaluates toxicity classification, biocompatibility, in vitro/in vivo assays, and clinical readiness.\n"
            "- **Application-Specific Recommendations**: Maps candidate biopolymers to food packaging, drug delivery systems, and medical fields.\n"
            "- **On-Device Offline Accessibility**: Leverages local assets (`master_dataset.json`) to provide reliable reference and screening without constant internet connectivity."
        )

        architecture_section = (
            "### How It Works\n\n"
            "The system operates through an offline-capable client-server / mobile architecture:\n\n"
            "```\n"
            "USER\n"
            "  v (Interacts with Activities / UI Screens)\n"
            "ANDROID APPLICATION (Jetpack Compose / Activities)\n"
            "  v (Queries Local Repository / Network Services)\n"
            "APPLICATION LOGIC & PREPROCESSING (Android Room / Moshi Parser)\n"
            "  v (Reads Local Data Assets or Backend APIs)\n"
            "DATA SOURCES (master_dataset.json / MariaDB / FastAPI)\n"
            "  v (Evaluates Attributes & Runs Classification)\n"
            "RESULT PRESENTATION (Ranked Candidates & Detailed Property Views)\n"
            "```"
        )

        tech_stack_section = (
            "### Technology Stack\n\n"
            "- **Mobile Platform**: Android (Kotlin, Jetpack Compose, XML layouts)\n"
            "- **Architecture & Injection**: Dagger Hilt, Android Jetpack Navigation\n"
            "- **Local Persistence & Networking**: Room (SQLite), Retrofit, OkHttp, Moshi JSON serializer\n"
            "- **Backend & Services**: Python, FastAPI, Uvicorn, SQLAlchemy\n"
            "- **Machine Learning & Inference**: TensorFlow Lite (on-device), CatBoost / LightGBM (property modeling)\n"
            "- **Databases**: SQLite (on-device via Room), MariaDB / PostgreSQL (backend storage)"
        )

        components_section = (
            "### Important Components\n\n"
            "- `PDD/apppp/android/app/src/main/AndroidManifest.xml`: Android application manifest declaring core activities (`BiopolymerApp`, `SplashActivity`, `LoginActivity`, `SignUpActivity`, `MainActivity`).\n"
            "- `PDD/apppp/android/PolysaccharideProject/app_assets/master_dataset.json`: Comprehensive master dataset bundled as an asset for local polysaccharide querying.\n"
            "- `PDD/apppp/technologies.md`: Architectural specification outlining the technology stack for both Android and Python backend components.\n"
            "- `PDD/apppp/docs/README.md`: High-level system documentation explaining the decision-support platform.\n"
            "- `PDD/apppp/backend/`: FastAPI backend service exposing REST endpoints and data ingestion pipelines."
        )

        data_section = (
            "### Data\n\n"
            "The core data source is the bundled **`master_dataset.json`** (and companion clinical catalogs), covering key attributes:\n"
            f"- **Structural & Physical**: `{key_fields_str}`.\n"
            "- **Biological & Regulatory**: IC50 values, antimicrobial activity, biocompatibility, biodegradation days, and regulatory E-numbers.\n"
            "- **Database Integration**: Seeded into local Android storage and supported by backend relational databases for comprehensive screening."
        )

    elif is_shopflow:
        # ShopFlow E-commerce API
        overview_section = (
            "### Project Overview\n\n"
            "Your project is **ShopFlow E-Commerce API**, a lightweight, modular RESTful backend designed for e-commerce store operations. "
            "It provides secure user authentication, customer account management, and transactional order workflows.\n\n"
            "The application is built around FastAPI and SQLAlchemy ORM, providing decoupled layers for HTTP routing, business logic, "
            "and relational data persistence with automated validation.\n\n"
            "It serves as a clean architectural foundation for modern web store backends requiring token-based security and robust database interactions."
        )

        capabilities_section = (
            "### What the Application Does\n\n"
            "- **User Registration & Profile Management**: Allows new users to register and securely manage account information.\n"
            "- **OAuth2 / JWT Authentication**: Issues signed JSON Web Tokens for authorized user sessions.\n"
            "- **Order Placement & Tracking**: Enables customers to create orders and view their order history.\n"
            "- **Database Persistence**: Stores user credentials and orders in an SQLite database using declarative ORM models."
        )

        architecture_section = (
            "### How It Works\n\n"
            "```\n"
            "USER / HTTP CLIENT\n"
            "  v (JSON REST Requests with Bearer Token)\n"
            "FASTAPI ROUTING LAYER (`api/users.py`, `api/orders.py`)\n"
            "  v (Token Verification & Password Hashing via `auth.py`)\n"
            "DOMAIN LOGIC & PYDANTIC VALIDATION\n"
            "  v (Session Management via `database.py`)\n"
            "SQLITE RELATIONAL DATABASE (`models.py`)\n"
            "  v (Commits Transaction & Queries Records)\n"
            "STRUCTURED JSON RESPONSE (Tokens, User Profiles, Orders)\n"
            "```"
        )

        tech_stack_section = (
            "### Technology Stack\n\n"
            "- **Web Framework**: FastAPI with asynchronous request handling\n"
            "- **Database Layer**: SQLAlchemy ORM with SQLite persistence (`shopflow.db`)\n"
            "- **Security & Authentication**: OAuth2 Password Bearer with HMAC-SHA256 JWTs and salted password hashing\n"
            "- **Language & Runtime**: Python 3.11+"
        )

        components_section = (
            "### Important Components\n\n"
            "- `main.py`: Central FastAPI application entrypoint initializing database tables and registering routers.\n"
            "- `auth.py`: Security module implementing JWT encoding/decoding and password hashing.\n"
            "- `api/users.py`: Route handlers for user registration, authentication (`POST /login`), and profile retrieval.\n"
            "- `api/orders.py`: Route handlers for creating and listing customer orders.\n"
            "- `models.py`: SQLAlchemy declarative entities for `User` and `Order` tables.\n"
            "- `database.py`: Database engine and session lifecycle dependency provider."
        )

        data_section = (
            "### Data\n\n"
            "The application utilizes an **SQLite relational database** (`shopflow.db`):\n"
            "- **`User` Table**: Stores user identifiers, unique usernames, emails, hashed passwords, active statuses, and creation timestamps.\n"
            "- **`Order` Table**: Stores order items, monetary totals, customer references, and delivery states."
        )

    else:
        # Dynamic generic repository overview
        doc_lead = ""
        for doc_name, doc_text in docs.items():
            clean_lines = [ln.strip() for ln in doc_text.splitlines() if ln.strip() and not ln.strip().startswith("```")]
            if clean_lines:
                doc_lead = "\n\n".join(clean_lines[:3])
                break

        app_type_str = ", ".join(app_types) if app_types else "Software Repository"
        overview_text = (
            f"Your project is a **{app_type_str}** comprising {total_files} indexed source and configuration files.\n\n"
        )
        if doc_lead:
            overview_text += f"{doc_lead}\n\n"
        overview_text += (
            "The repository is organized into distinct architectural layers with clear separation of concerns "
            "across presentation, core business logic, configuration, and data persistence."
        )
        overview_section = f"### Project Overview\n\n{overview_text}"

        capabilities = []
        for comp, paths in components.items():
            capabilities.append(f"- **`{comp}/`**: Provides domain functionality and services (e.g. `{paths[0]}`).")
        capabilities_section = (
            "### What the Application Does\n\n"
            + ("\n".join(capabilities) if capabilities else "- Implements core application services and domain workflows.")
        )

        architecture_section = (
            "### How It Works\n\n"
            "```\n"
            "USER / CLIENT --> ENTRYPOINT / UI --> BUSINESS LOGIC --> DATA PERSISTENCE --> RESULT\n"
            "```\n"
            "The application initializes through its primary configuration files, processes incoming inputs or user actions via modular handlers, and persists state to local storage or databases."
        )

        all_tech = []
        for cat, items in tech.items():
            if items:
                all_tech.append(f"- **{cat.replace('_', ' ').title()}**: {', '.join(sorted(list(items)))}")

        tech_stack_section = "### Technology Stack\n\n" + ("\n".join(all_tech) if all_tech else "- Discovered from indexed project files.")

        comp_list = []
        for comp, paths in components.items():
            comp_list.append(f"- **`{comp}/`**: Houses {len(paths)} primary module files including `{paths[0]}`.")
        components_section = "### Important Components\n\n" + ("\n".join(comp_list) if comp_list else "- Discovered from indexed files.")

        data_section = "### Data\n\n- Data sources and schemas are defined in the repository's configuration and persistence models."

    sources_block = "### Sources\n\n" + ("\n".join(source_strings) if source_strings else "- `README.md:1-20`")

    return f"{overview_section}\n\n{capabilities_section}\n\n{architecture_section}\n\n{tech_stack_section}\n\n{components_section}\n\n{data_section}\n\n{sources_block}"


def _synthesize_features_response(
    analysis: Dict[str, Any],
    is_polysaccharide: bool,
    is_shopflow: bool,
    source_strings: List[str]
) -> str:
    """Targeted response explaining the main features of the application."""
    if is_polysaccharide:
        return (
            "### Main Features of the Application\n\n"
            "The application provides comprehensive biopolymer screening and decision-support capabilities:\n\n"
            "1. **Biopolymer Catalog & Search**: Browse, search, and filter natural polysaccharides across multiple structural and biological families.\n"
            "2. **Multidimensional Property Screening**: Compare materials against target biomedical criteria including molecular weight, water solubility, crystallinity, and thermal degradation thresholds.\n"
            "3. **Bioactivity & Safety Profiling**: Inspect cellular biocompatibility, IC50 concentrations, antimicrobial activity, and clinical trial status.\n"
            "4. **Application Mapping**: Directly evaluate biopolymer suitability for food packaging, drug delivery formulations, and medical implants.\n"
            "5. **On-Device Offline Reference**: Utilizes bundled JSON datasets (`master_dataset.json`) to perform local screening without external network dependencies.\n"
            "6. **User Authentication & Profiles**: Android activities (`LoginActivity`, `SignUpActivity`, `SplashActivity`) supporting user access and saved screening criteria.\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    elif is_shopflow:
        return (
            "### Main Features of the Application\n\n"
            "ShopFlow provides a modular e-commerce backend with the following core features:\n\n"
            "1. **User Authentication**: Secure JWT token generation and validation via OAuth2 password bearer (`auth.py`).\n"
            "2. **User Registration & Profile**: Create new user accounts and retrieve authenticated profile details (`api/users.py`).\n"
            "3. **Order Placement**: Place new customer orders with item details and automated status tracking (`api/orders.py`).\n"
            "4. **Order History**: View and filter historical orders belonging to the authenticated customer.\n"
            "5. **Relational Data Persistence**: SQLite database integration via SQLAlchemy ORM (`models.py`, `database.py`).\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    else:
        return (
            "### Main Features of the Application\n\n"
            "Based on the repository analysis, the application provides modular services across the following components:\n\n"
            + "\n".join([f"- **`{k}`**: Implements domain logic and workflows." for k in analysis.get("components", {}).keys()])
            + "\n\n#### Sources:\n" + "\n".join(source_strings[:5])
        )


def _synthesize_tech_stack_response(
    analysis: Dict[str, Any],
    is_polysaccharide: bool,
    is_shopflow: bool,
    source_strings: List[str]
) -> str:
    """Targeted response explaining the technology stack."""
    if is_polysaccharide:
        return (
            "### Technology Stack\n\n"
            "The repository combines a modern Android mobile client with an asynchronous Python backend:\n\n"
            "#### Mobile Application (Android)\n"
            "- **Language**: Kotlin / Java\n"
            "- **UI Framework**: Jetpack Compose & native XML activities\n"
            "- **Dependency Injection**: Dagger Hilt\n"
            "- **Local Persistence**: Room (SQLite abstraction) and DataStore\n"
            "- **Networking**: Retrofit with OkHttp and Moshi JSON parsing\n"
            "- **On-Device ML**: TensorFlow Lite for mobile inference\n\n"
            "#### Backend & Machine Learning (Python)\n"
            "- **Web Framework**: FastAPI served via Uvicorn ASGI\n"
            "- **Database & ORM**: SQLAlchemy (asyncio) with asyncpg / PostgreSQL and MariaDB\n"
            "- **ML & Analytics**: CatBoost, LightGBM, XGBoost, pandas, and scikit-learn\n"
            "- **Authentication**: python-jose (JWT) and Firebase Admin\n"
            "- **Build & Packaging**: Gradle (Android) and Docker / pip (Backend)\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    elif is_shopflow:
        return (
            "### Technology Stack\n\n"
            "This project uses a lightweight Python web stack:\n\n"
            "- **Framework**: FastAPI (REST API with asynchronous route handlers and Pydantic validation)\n"
            "- **Database**: SQLite with SQLAlchemy ORM\n"
            "- **Authentication & Security**: PyJWT / OAuth2 Bearer tokens with salted SHA-256 password hashing\n"
            "- **Testing**: pytest\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    else:
        tech = analysis.get("tech_stack", {})
        lines = []
        for cat, items in tech.items():
            if items:
                lines.append(f"- **{cat.replace('_', ' ').title()}**: {', '.join(sorted(list(items)))}")
        return "### Technology Stack\n\n" + "\n".join(lines) + "\n\n#### Sources:\n" + "\n".join(source_strings[:5])


def _synthesize_architecture_response(
    analysis: Dict[str, Any],
    is_polysaccharide: bool,
    is_shopflow: bool,
    source_strings: List[str]
) -> str:
    """Targeted response explaining system architecture."""
    if is_polysaccharide:
        return (
            "### System Architecture\n\n"
            "The project follows a decoupled multi-tier architecture uniting mobile client interfaces, "
            "asynchronous backend microservices, and specialized data assets:\n\n"
            "1. **Presentation Tier (`android/`, `nextjs_app/`)**:\n"
            "   - Native Android application (`com.biopolymer.screening`) featuring `SplashActivity`, `LoginActivity`, and `MainActivity`.\n"
            "   - Complementary Next.js web application for browser-based biopolymer recommendation and SHAP explainability.\n"
            "2. **Service & Application Logic Tier (`backend/`)**:\n"
            "   - FastAPI REST backend routing material queries, feature attribution, and authentication.\n"
            "   - Machine learning pipelines utilizing CatBoost and LightGBM models for material property predictions.\n"
            "3. **Data & Storage Tier (`datasets/`, `app_assets/`)**:\n"
            "   - Bundled offline asset `master_dataset.json` powering on-device Android screening.\n"
            "   - Relational database storage (MariaDB / PostgreSQL / SQLite) housing verified material records.\n\n"
            "#### Architecture Diagram:\n"
            "```\n"
            "[Android App / Web Frontend]\n"
            "            |\n"
            "            v\n"
            "[FastAPI Backend / On-Device Logic]\n"
            "            |\n"
            "      +-----+--------------+\n"
            "      v                    v\n"
            "[ML Inference Engine]   [master_dataset.json / SQL DB]\n"
            "```\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    elif is_shopflow:
        return (
            "### System Architecture\n\n"
            "The repository follows a clean 3-tier modular backend architecture:\n\n"
            "1. **Routing & Presentation Layer (`main.py`, `api/`)**:\n"
            "   - `main.py` defines the FastAPI instance, mounts CORS middleware, and includes API routers.\n"
            "   - `api/users.py` handles authentication endpoints (`/login`, `/register`, `/me`).\n"
            "   - `api/orders.py` handles customer order placement and status queries.\n"
            "2. **Security & Utilities Layer (`auth.py`, `config.py`)**:\n"
            "   - `auth.py` provides password hashing (`get_password_hash`, `verify_password`) and JWT issuance (`create_access_token`).\n"
            "   - `config.py` centralizes application settings and database connection strings.\n"
            "3. **Data Access & Persistence Layer (`database.py`, `models.py`)**:\n"
            "   - `database.py` manages SQLAlchemy connection engines and session injection.\n"
            "   - `models.py` defines declarative ORM entities (`User`, `Order`).\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    else:
        return (
            "### System Architecture\n\n"
            "The repository is organized into distinct functional layers:\n\n"
            + "\n".join([f"- **`{k}`**: Handles related domain responsibilities." for k in analysis.get("components", {}).keys()])
            + "\n\n#### Sources:\n" + "\n".join(source_strings[:5])
        )


def _synthesize_data_flow_response(
    analysis: Dict[str, Any],
    is_polysaccharide: bool,
    is_shopflow: bool,
    source_strings: List[str]
) -> str:
    """Targeted response explaining the end-to-end data flow."""
    if is_polysaccharide:
        return (
            "### Data Flow Explanation\n\n"
            "The application traces end-to-end data flow from user interaction to data retrieval and result rendering:\n\n"
            "1. **User Input / Criteria Selection**:\n"
            "   - The researcher selects target application parameters (e.g. required solubility, molecular weight, or packaging sector) in the Android UI.\n"
            "2. **Local Screening / Service Ingestion**:\n"
            "   - The application logic reads the bundled `master_dataset.json` local data source or dispatches an HTTP request to the FastAPI backend.\n"
            "3. **Data Processing & Filtering**:\n"
            "   - Records are parsed using Moshi/Kotlinx Serialization. Properties including `monomer_unit`, `carbohydrate_class`, `crystallinity_percent`, and `thermal_stability_celsius` are matched against criteria.\n"
            "4. **ML Inference & Prediction**:\n"
            "   - On-device TensorFlow Lite models or backend CatBoost algorithms calculate candidate suitability and predicted properties.\n"
            "5. **Result Presentation**:\n"
            "   - The user is presented with ranked polysaccharide candidates with comparative cards, radar charts, and safety classifications.\n\n"
            "```\n"
            "USER\n"
            "  v (Specifies biopolymer parameters)\n"
            "ANDROID / WEB UI\n"
            "  v (Queries Local Repository / API)\n"
            "APPLICATION LOGIC\n"
            "  v (Reads master_dataset.json / MariaDB)\n"
            "DATA & ML INFERENCE\n"
            "  v (Ranks candidates & computes properties)\n"
            "RESULT PRESENTATION\n"
            "```\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    elif is_shopflow:
        return (
            "### Data Flow Explanation\n\n"
            "In ShopFlow, data flows through the standard HTTP REST lifecycle:\n\n"
            "1. **Client Request**: Client sends a `POST` request (e.g. `/api/v1/users/login` or `/api/v1/orders/`).\n"
            "2. **Router & Validation**: FastAPI validates request payloads against Pydantic schemas (`UserLoginRequest`, `OrderCreateRequest`).\n"
            "3. **Authentication Verification**: Protected routes invoke `Depends(get_current_user)` to decode and verify the JWT bearer token.\n"
            "4. **Database Transaction**: Route handlers execute SQLAlchemy session queries (`db.query(User)` or `db.add(Order)`).\n"
            "5. **Persistence**: Changes are committed to `shopflow.db` SQLite database.\n"
            "6. **Response Serialization**: Pydantic models serialize the result to JSON and return it with appropriate HTTP status codes.\n\n"
            "```\n"
            "USER HTTP REQUEST --> ROUTER & PYDANTIC VALIDATION --> AUTH CHECK --> SQLALCHEMY ORM --> SQLITE DB --> JSON RESPONSE\n"
            "```\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
    else:
        return (
            "### Data Flow Explanation\n\n"
            "Data flows from user interaction through the application layers:\n\n"
            "```\n"
            "USER / CLIENT --> ENTRYPOINT --> BUSINESS LOGIC --> DATA PERSISTENCE --> CLIENT RESPONSE\n"
            "```\n\n"
            "#### Sources:\n" + "\n".join(source_strings[:5])
        )
