# Frontend Integration Guide

## Overview

I've created React components to connect your existing TomeHub frontend with the new Flask backend API for RAG search and document ingestion.

## New Files Created

### 1. Backend API Service
**File:** `services/backendApiService.ts`

TypeScript service for communicating with Flask backend:
- `checkApiHealth()` - Check if backend is online
- `searchLibrary()` - RAG search endpoint
- `ingestDocument()` - Document ingestion endpoint

### 2. RAG Search Component
**File:** `components/RAGSearch.tsx`

Beautiful search interface with:
- Question input with search icon
- Loading states
- AI-generated answers
- Source citations with page numbers
- Example questions
- Error handling
- Full Tailwind CSS styling

### 3. Document Ingest Component
**File:** `components/DocumentIngest.tsx`

Document upload interface with:
- PDF path input
- Title and author fields
- Progress indicators
- Success/error messages
- Info about the ingestion process
- Full Tailwind CSS styling

## Integration Steps

### Step 1: Add to Sidebar

Update `components/Sidebar.tsx` to add new menu items:

```tsx
// Add these imports at the top
import { Search, Upload } from 'lucide-react';

// Add these menu items in the sidebar navigation
<button
  onClick={() => onTabChange('RAG_SEARCH')}
  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
    activeTab === 'RAG_SEARCH'
      ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400'
      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
  }`}
>
  <Search className="w-5 h-5" />
  <span className="font-medium">RAG Search</span>
</button>

<button
  onClick={() => onTabChange('INGEST')}
  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
    activeTab === 'INGEST'
      ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400'
      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
  }`}
>
  <Upload className="w-5 h-5" />
  <span className="font-medium">Ingest Document</span>
</button>
```

### Step 2: Update App.tsx

Add the new components to your main app:

```tsx
// Add imports at the top
import { RAGSearch } from './components/RAGSearch';
import { DocumentIngest } from './components/DocumentIngest';

// Update the activeTab type to include new tabs
const [activeTab, setActiveTab] = useState<
  ResourceType | "NOTES" | "DASHBOARD" | "PROFILE" | "RAG_SEARCH" | "INGEST"
>("DASHBOARD");

// Add routing for new components in the main content area
{activeTab === "PROFILE" ? (
  <ProfileView ... />
) : activeTab === "RAG_SEARCH" ? (
  <RAGSearch userId={userId} />
) : activeTab === "INGEST" ? (
  <DocumentIngest userId={userId} />
) : view === "list" ? (
  <BookList ... />
) : (
  ...
)}
```

### Step 3: Start Backend Server

Before using the new features, start the Flask backend:

```bash
# In a separate terminal
python backend/app.py
```

The backend will run on `http://localhost:5000`

### Step 4: Start Frontend

```bash
npm run dev
```

## Usage

### RAG Search

1. Click "RAG Search" in the sidebar
2. Enter a question about your library
3. Click "Search" or press Enter
4. View AI-generated answer with source citations

**Example questions:**
- "What is phenomenology?"
- "What does Heidegger say about being-in-the-world?"
- "Summarize the main ideas about Stoicism"

### Document Ingestion

1. Click "Ingest Document" in the sidebar
2. Enter the full path to your PDF file
3. Enter the book title and author
4. Click "Ingest Document"
5. Wait for processing (may take several minutes)
6. Document becomes searchable via RAG Search

## API Configuration

The API base URL is configured in `services/backendApiService.ts`:

```typescript
const API_BASE_URL = 'http://localhost:5000';
```

For production, update this to your deployed backend URL.

## Features

### RAG Search Component
✅ Clean, modern UI with Tailwind CSS  
✅ Real-time search with loading states  
✅ Formatted AI answers  
✅ Source citations with page numbers  
✅ Relevance scores  
✅ Example questions  
✅ Error handling  
✅ Dark mode support  

### Document Ingest Component
✅ Simple form interface  
✅ File path input  
✅ Title and author fields  
✅ Progress indicators  
✅ Success/error messages  
✅ Process explanation  
✅ Dark mode support  

## Troubleshooting

### "Search failed" error
- Ensure Flask backend is running (`python backend/app.py`)
- Check that you have ingested documents for your user ID
- Verify GEMINI_API_KEY is configured in `backend/.env`

### "Ingestion failed" error
- Check PDF file path is correct and accessible
- Ensure OCI credentials are configured
- Verify all backend services are running

### CORS errors
- Flask backend has CORS enabled for `localhost:5173` and `localhost:3000`
- If using a different port, update CORS settings in `backend/app.py`

## Next Steps

1. **Add to Sidebar**: Follow Step 1 above
2. **Update App.tsx**: Follow Step 2 above
3. **Test RAG Search**: Ingest a document and try searching
4. **Customize Styling**: Modify Tailwind classes as needed
5. **Add Features**: Extend components with additional functionality

## Component Props

### RAGSearch
```typescript
interface RAGSearchProps {
  userId: string;  // Firebase user ID
}
```

### DocumentIngest
```typescript
interface DocumentIngestProps {
  userId: string;  // Firebase user ID
}
```

## API Response Types

### Search Response
```typescript
{
  answer: string;
  sources: Array<{
    title: string;
    page_number: number;
    similarity_score: number;
  }>;
  timestamp: string;
}
```

### Ingest Response
```typescript
{
  success: boolean;
  message: string;
  timestamp: string;
}
```
