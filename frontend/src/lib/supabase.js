import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://lixjwweoxuzwjajyzqvr.supabase.co'
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpeGp3d2VveHV6d2phanl6cXZyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODcyMjI2MDUsImV4cCI6MjEwMjc5ODYwNX0.7Oz339VPqpufmwWbmXev8q-mlOAA2BiLa3SRAhfEAGU'

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
