import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { ScreenState } from './ScreenState';

interface ErrorStatePanelProps {
    title?: string;
    message: string;
    retryLabel?: string;
    onRetry?: () => void;
    fullScreen?: boolean;
}

export const ErrorStatePanel: React.FC<ErrorStatePanelProps> = ({
    title = 'Something went wrong',
    message,
    retryLabel = 'Try again',
    onRetry,
    fullScreen = false,
}) => {
    return (
        <ScreenState
            mode="error"
            icon={<AlertTriangle className="h-8 w-8 text-red-500" />}
            title={title}
            message={message}
            actionLabel={onRetry ? retryLabel : undefined}
            onAction={onRetry}
            fullScreen={fullScreen}
        />
    );
};
