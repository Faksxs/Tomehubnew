import React from 'react';

interface NoteMoveUndoToastProps {
  onUndo: () => void;
}

export const NoteMoveUndoToast: React.FC<NoteMoveUndoToastProps> = ({ onUndo }) => {
  return (
    <div className="fixed bottom-5 right-5 z-50 bg-[#262D40] text-white px-4 py-3 rounded-xl shadow-xl border border-white/10 flex items-center gap-3">
      <span className="text-sm">Note moved.</span>
      <button
        onClick={onUndo}
        className="text-sm font-semibold text-[#FFB58D] hover:text-white"
      >
        Undo
      </button>
    </div>
  );
};
