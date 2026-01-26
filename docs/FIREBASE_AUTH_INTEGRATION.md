# Firebase Authentication Integration Guide

## Overview

Your TomeHub backend now integrates seamlessly with Firebase Authentication. The authenticated user's UID is automatically used for all backend operations.

## Updated Components

### 1. Backend API Service (`services/backendApiService.ts`)
✅ Added authentication validation  
✅ Requires `firebaseUid` for all operations  
✅ Throws error if user is not authenticated  

### 2. RAG Search Component (`components/RAGSearch.tsx`)
✅ Accepts `userId` and `userEmail` props  
✅ Displays authenticated user email  
✅ Uses Firebase UID for backend calls  

### 3. Document Ingest Component (`components/DocumentIngest.tsx`)
✅ Accepts `userId` and `userEmail` props  
✅ Displays authenticated user email  
✅ Uses Firebase UID for backend calls  

## Integration in App.tsx

Update your `App.tsx` to pass the authenticated user's information:

```tsx
// In the Layout component, where you render the components:

{activeTab === "RAG_SEARCH" ? (
  <RAGSearch 
    userId={userId}        // Firebase UID from AuthContext
    userEmail={userEmail}  // Firebase email from AuthContext
  />
) : activeTab === "INGEST" ? (
  <DocumentIngest 
    userId={userId}        // Firebase UID from AuthContext
    userEmail={userEmail}  // Firebase email from AuthContext
  />
) : ...}
```

## How It Works

### 1. User Authentication Flow
```
1. User logs in with Google (Firebase Auth)
   ↓
2. Firebase provides user.uid and user.email
   ↓
3. App.tsx passes userId and userEmail to components
   ↓
4. Components use userId for backend API calls
```

### 2. Backend Data Isolation
```
1. User searches/ingests with their Firebase UID
   ↓
2. Backend stores data with firebase_uid field
   ↓
3. Database queries filter by firebase_uid
   ↓
4. Users only see their own data
```

## Example Usage

### RAG Search
```tsx
import { RAGSearch } from './components/RAGSearch';
import { useAuth } from './contexts/AuthContext';

function MyComponent() {
  const { user } = useAuth();
  
  return (
    <RAGSearch 
      userId={user.uid}
      userEmail={user.email}
    />
  );
}
```

### Document Ingest
```tsx
import { DocumentIngest } from './components/DocumentIngest';
import { useAuth } from './contexts/AuthContext';

function MyComponent() {
  const { user } = useAuth();
  
  return (
    <DocumentIngest 
      userId={user.uid}
      userEmail={user.email}
    />
  );
}
```

## Security Features

✅ **Authentication Required**: All backend operations require valid Firebase UID  
✅ **Data Isolation**: Users can only access their own data  
✅ **User Display**: Shows which account is being used  
✅ **Error Handling**: Clear error messages for authentication issues  

## Testing

### 1. Test with Different Users
1. Log in with Google Account A
2. Ingest a document
3. Search for content
4. Log out
5. Log in with Google Account B
6. Verify you don't see Account A's data

### 2. Test Authentication Errors
The components will throw errors if:
- User is not authenticated
- Firebase UID is missing
- Backend API is unreachable

## Database Structure

Each record in `TOMEHUB_CONTENT` includes:
```sql
firebase_uid VARCHAR2(128) NOT NULL  -- User's Firebase UID
```

This ensures:
- Multi-tenant support
- Data privacy
- User-specific searches

## Next Steps

1. ✅ Update `App.tsx` with the code above
2. ✅ Test login with your Google account
3. ✅ Ingest a test document
4. ✅ Search your library
5. ✅ Test with multiple accounts (optional)

Your backend now automatically uses the authenticated user's Firebase UID for all operations!
