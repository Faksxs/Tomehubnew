import React from 'react';
import { ScreenState } from '../../shared/ui/states/ScreenState';

interface EmptyStatePanelProps {
  icon: React.ReactNode;
  title: string;
  message: string;
}

export const EmptyStatePanel: React.FC<EmptyStatePanelProps> = ({
  icon,
  title,
  message,
}) => {
  return <ScreenState mode="empty" icon={icon} title={title} message={message} />;
};
