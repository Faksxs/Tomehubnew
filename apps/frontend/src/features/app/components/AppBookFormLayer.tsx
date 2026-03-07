import React from 'react';
import { BookForm } from '../../../components/BookForm';
import { LibraryItem } from '../../../types';
import { AppTab, PersonalNoteDraftDefaults } from '../types';
import { resolveAppFormInitialType } from '../stateHelpers';

interface AppBookFormLayerProps {
    isOpen: boolean;
    editingBook?: LibraryItem;
    editingBookId: string | null;
    activeTab: AppTab;
    personalNoteDraftDefaults: PersonalNoteDraftDefaults;
    onSave: (item: Omit<LibraryItem, 'highlights'>) => void;
    onUpdate: (item: Omit<LibraryItem, 'highlights'>) => void;
    onClose: () => void;
}

export const AppBookFormLayer: React.FC<AppBookFormLayerProps> = ({
    isOpen,
    editingBook,
    editingBookId,
    activeTab,
    personalNoteDraftDefaults,
    onSave,
    onUpdate,
    onClose,
}) => {
    if (!isOpen) return null;

    return (
        <BookForm
            initialType={resolveAppFormInitialType(editingBook?.type, activeTab)}
            initialData={editingBook}
            noteDefaults={!editingBook && activeTab === 'PERSONAL_NOTE'
                ? personalNoteDraftDefaults
                : undefined}
            onSave={editingBookId ? onUpdate : onSave}
            onCancel={onClose}
        />
    );
};
