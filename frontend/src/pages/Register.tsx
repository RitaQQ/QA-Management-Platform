import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [orgName, setOrgName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await register(orgName, username, email, password);
      navigate('/dashboard');
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } };
      setError(axiosError.response?.data?.error || 'Registration failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0D1117] px-4">
      <Card className="w-full max-w-md border-[#30363D] bg-[#161B22]">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <Badge className="bg-[#238636]/20 text-[#3FB950] border-[#238636]/40 hover:bg-[#238636]/20">
              14-day free trial
            </Badge>
          </div>
          <CardTitle className="text-2xl font-bold text-[#C9D1D9]">
            Create your account
          </CardTitle>
          <CardDescription className="text-[#8B949E]">
            Get started with your QA management platform
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="orgName" className="text-[#C9D1D9]">
                Organization Name
              </Label>
              <Input
                id="orgName"
                type="text"
                placeholder="Your company or team name"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                required
                className="border-[#30363D] bg-[#0D1117] text-[#C9D1D9] placeholder:text-[#484F58] focus:border-[#238636] focus:ring-[#238636]"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="username" className="text-[#C9D1D9]">
                Username
              </Label>
              <Input
                id="username"
                type="text"
                placeholder="Choose a username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="border-[#30363D] bg-[#0D1117] text-[#C9D1D9] placeholder:text-[#484F58] focus:border-[#238636] focus:ring-[#238636]"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className="text-[#C9D1D9]">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="border-[#30363D] bg-[#0D1117] text-[#C9D1D9] placeholder:text-[#484F58] focus:border-[#238636] focus:ring-[#238636]"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-[#C9D1D9]">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="Create a strong password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="border-[#30363D] bg-[#0D1117] text-[#C9D1D9] placeholder:text-[#484F58] focus:border-[#238636] focus:ring-[#238636]"
              />
            </div>
            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-[#238636] text-white hover:bg-[#2ea043] disabled:opacity-50"
            >
              {isSubmitting ? 'Creating account...' : 'Create Account'}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-[#8B949E]">
            Already have an account?{' '}
            <Link to="/login" className="text-[#58A6FF] hover:underline">
              Sign in
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
