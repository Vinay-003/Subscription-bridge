import "./globals.css";
import { Inter } from "next/font/google";

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title:" "SHOESY | Elite Footwear',
  description:" "Step into luxury.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="bg-black text-white">
      {children}
    
  );
}