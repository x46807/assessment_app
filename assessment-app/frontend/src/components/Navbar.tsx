'use client';

import React from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { GoogleLogin } from "@react-oauth/google";
import { BookOpen, LogOut } from "lucide-react";

export default function Navbar() {
  const { user, loginWithGoogle, logout } = useAuth();

  return (
    <nav className="border-b border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center space-x-3">
          <div className="bg-indigo-600 p-2 rounded-lg text-white">
            <BookOpen className="h-5 w-5" />
          </div>
          <span className="font-bold text-lg text-slate-900 tracking-tight">
            AssessAI <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 ml-1">Psychometric</span>
          </span>
        </Link>

        <div>
          {user ? (
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                {user.avatar_url && (
                  <img src={user.avatar_url} alt={user.full_name} className="w-8 h-8 rounded-full border border-slate-200" />
                )}
                <span className="text-sm font-medium text-slate-700 hidden sm:inline">{user.full_name}</span>
              </div>
              <button onClick={logout} className="p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <GoogleLogin onSuccess={loginWithGoogle} onError={() => console.error("Login Failed")} useOneTap />
          )}
        </div>
      </div>
    </nav>
  );
}
