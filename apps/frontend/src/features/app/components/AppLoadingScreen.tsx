import React from 'react';
import { ScreenState } from '../../../shared/ui/states/ScreenState';

interface AppLoadingScreenProps {
    message: string;
}

export const AppLoadingScreen: React.FC<AppLoadingScreenProps> = ({ message }) => {
    return <ScreenState mode="loading" title={message} fullScreen />;
};
