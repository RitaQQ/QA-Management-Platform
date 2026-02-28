import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type Variant = 'api' | 'testcase' | 'project' | 'result' | 'priority';

const colorMap: Record<Variant, Record<string, string>> = {
  api: {
    healthy: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    unhealthy: 'bg-red-500/20 text-red-400 border-red-500/30',
    unknown: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  },
  testcase: {
    draft: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    ready: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    in_progress: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    completed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    blocked: 'bg-red-500/20 text-red-400 border-red-500/30',
  },
  project: {
    draft: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    in_progress: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    completed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  },
  result: {
    pass: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    fail: 'bg-red-500/20 text-red-400 border-red-500/30',
    blocked: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    not_tested: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  },
  priority: {
    high: 'bg-red-500/20 text-red-400 border-red-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  },
};

interface StatusBadgeProps {
  status: string;
  variant: Variant;
  className?: string;
}

export function StatusBadge({ status, variant, className }: StatusBadgeProps) {
  const colors = colorMap[variant]?.[status] ?? 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  const label = status.replace(/_/g, ' ');

  return (
    <Badge variant="outline" className={cn('capitalize text-xs', colors, className)}>
      {label}
    </Badge>
  );
}
