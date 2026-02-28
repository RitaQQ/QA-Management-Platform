import { useState, useEffect, type FormEvent } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import api from '@/services/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Loader2 } from 'lucide-react';

export default function Join() {
  const { joinViaInvite } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [orgName, setOrgName] = useState('');
  const [role, setRole] = useState('');
  const [validating, setValidating] = useState(true);
  const [tokenError, setTokenError] = useState('');

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setTokenError('No invite token provided.');
      setValidating(false);
      return;
    }
    api
      .get(`/auth/invite/${token}`)
      .then((res) => {
        setOrgName(res.data.data.organization_name);
        setRole(res.data.data.role);
      })
      .catch((err) => {
        setTokenError(
          err.response?.data?.error || 'Invalid or expired invite link.'
        );
      })
      .finally(() => setValidating(false));
  }, [token]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await joinViaInvite(token, username, email, password);
      navigate('/dashboard');
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } };
      setError(
        axiosError.response?.data?.error || 'Failed to join. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  if (validating) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0D1117]">
        <Loader2 className="h-8 w-8 animate-spin text-[#8B949E]" />
      </div>
    );
  }

  if (tokenError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0D1117] px-4">
        <Card className="w-full max-w-md border-[#30363D] bg-[#161B22]">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl font-bold text-[#C9D1D9]">
              Invalid Invite
            </CardTitle>
            <CardDescription className="text-red-400">
              {tokenError}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Link to="/login" className="text-[#58A6FF] hover:underline text-sm">
              Go to login
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0D1117] px-4">
      <Card className="w-full max-w-md border-[#30363D] bg-[#161B22]">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-bold text-[#C9D1D9]">
            Join {orgName}
          </CardTitle>
          <CardDescription className="text-[#8B949E]">
            You&apos;ve been invited to join as <span className="text-[#C9D1D9] font-medium capitalize">{role}</span>
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
              <Label htmlFor="username" className="text-[#C9D1D9]">Username</Label>
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
              <Label htmlFor="email" className="text-[#C9D1D9]">Email</Label>
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
              <Label htmlFor="password" className="text-[#C9D1D9]">Password</Label>
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
              {isSubmitting ? 'Joining...' : 'Join Organization'}
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
