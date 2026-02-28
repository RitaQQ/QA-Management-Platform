import { useState, type FormEvent } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Clock } from 'lucide-react';

export default function Upgrade() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    // In a real app this would call an API endpoint
    setSubmitted(true);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0D1117] px-4">
      <Card className="w-full max-w-md border-[#30363D] bg-[#161B22]">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <div className="rounded-full bg-[#D29922]/10 p-3">
              <Clock className="h-8 w-8 text-[#D29922]" />
            </div>
          </div>
          <CardTitle className="text-2xl font-bold text-[#C9D1D9]">
            Trial Period Ended
          </CardTitle>
          <CardDescription className="text-[#8B949E]">
            Your 14-day free trial has expired. Paid plans are coming soon.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {submitted ? (
            <div className="rounded-md border border-[#238636]/30 bg-[#238636]/10 p-4 text-center">
              <p className="text-[#3FB950] font-medium">You&apos;re on the list!</p>
              <p className="text-[#8B949E] text-sm mt-1">
                We&apos;ll notify you at <span className="text-[#C9D1D9]">{email}</span> when
                paid plans become available.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="waitlist-email" className="text-[#C9D1D9]">
                  Email address
                </Label>
                <Input
                  id="waitlist-email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="border-[#30363D] bg-[#0D1117] text-[#C9D1D9] placeholder:text-[#484F58] focus:border-[#238636] focus:ring-[#238636]"
                />
              </div>
              <Button
                type="submit"
                className="w-full bg-[#238636] text-white hover:bg-[#2ea043]"
              >
                Join Waitlist
              </Button>
              <p className="text-center text-xs text-[#484F58]">
                We&apos;ll notify you when paid plans are available.
              </p>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
