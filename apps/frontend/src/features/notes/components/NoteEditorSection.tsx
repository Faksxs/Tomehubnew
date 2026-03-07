import React from 'react';
import { PersonalNoteEditor } from '../../../components/PersonalNoteEditor';

interface NoteEditorSectionProps {
    labelClass: string;
    helperClass: string;
    value: string;
    onChange: (value: string) => void;
    onSlashCommand: ({ command, query, selectedId }: { command: 'template' | 'link'; query?: string; selectedId?: string }) => void;
    slashTemplateItems: Array<{ id: string; label: string }>;
}

export const NoteEditorSection: React.FC<NoteEditorSectionProps> = ({
    labelClass,
    helperClass,
    value,
    onChange,
    onSlashCommand,
    slashTemplateItems,
}) => {
    return (
        <div className="mb-4 flex-1 flex flex-col">
            <label className={`block text-sm font-medium mb-1 ${labelClass}`}>
                Content
            </label>
            <PersonalNoteEditor
                value={value}
                onChange={onChange}
                minHeight={420}
                onSlashCommand={onSlashCommand}
                slashTemplateItems={slashTemplateItems}
                maxSlashSuggestions={20}
            />
            <p className={`mt-1 text-[10px] ${helperClass}`}>
                Toolbar supports heading, bold, underline, bullet list, numbered list and checklist.
                Hizli sablon icin: /task &lt;sablon-adi&gt; (orn: /task kitap)
            </p>
        </div>
    );
};
