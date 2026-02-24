// Oracle-only cutover compatibility shim.
// Intentionally keeps the old module path so any stale imports do NOT hit Firestore.
// Firebase remains auth-only; item/folder data operations are routed to backend Oracle APIs.

export {
  fetchItemsForUser,
  saveItemForUser,
  deleteItemForUser,
  deleteMultipleItemsForUser,
  fetchPersonalNoteFoldersForUser,
  savePersonalNoteFolderForUser,
  updatePersonalNoteFolderForUser,
  deletePersonalNoteFolderForUser,
  movePersonalNoteForUser,
} from "./oracleLibraryService";

