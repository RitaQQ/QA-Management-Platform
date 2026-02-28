import { type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ icon: Icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Icon className="h-12 w-12 text-[#8B949E] mb-4" />
      <h3 className="text-lg font-semibold text-[#C9D1D9] mb-2">{title}</h3>
      <p className="text-sm text-[#8B949E] mb-6 max-w-md">{description}</p>
      {actionLabel && onAction && (
        <Button onClick={onAction} className="bg-[#238636] hover:bg-[#2ea043]">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
