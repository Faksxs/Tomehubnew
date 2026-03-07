import React from 'react';
import { ScreenState } from '../../shared/ui/states/ScreenState';

interface CenteredLoadingStateProps {
  label?: string;
}

export const CenteredLoadingState: React.FC<CenteredLoadingStateProps> = ({
  label = 'Loading...',
}) => {
  return <ScreenState mode="loading" title={label} />;
};
