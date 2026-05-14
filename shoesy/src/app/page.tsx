"use client";

import { motion } from "framer-motion";
import { ShoppingBag, ArrowRight } from "lucide-react";
import products from "../data/products.json";

export default function Home() {
  return (
    <main className="min-h-screen">
      
      <section className="relative h-screen flex items-center justify-center overflow-hidden">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1 }}
          className="z-10 text-center"
        >
          <h1 className="text-8xl font-black tracking-tighter mb-4 italic text-transparent bg-clip-text bg-gradient-to-r from-white via-gray-400 to-gray-600">
            SHOESY
          
          <p className="text-xl tracking-[0.5em] uppercase text-gray-400 mb-8">The pinnacle of gait
          <button className="px-8 py-3 bg-white text-black font-bold uppercase tracking-widest hover:bg-gray-200 transition-colors flex items-center gap-2 mx-auto">
            Explore Collection 
          
        </motion.div>
        <motion.div 
          initial={{ scale: 1.2, opacity: 0 }}
          animate={{ scale: 1, opacity: 0.3 }}
          transition={{ duration: 2 }}
          className="absolute inset-0 z-0"
        >
          <img 
            src="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&q=80&w=2000" 
            alt="Hero Background" 
            className="w-full h-full object-cover"
          />
        </motion.div>
      

      
      <section className="max-w-7xl mx-auto py-32 px-6">
        <h2 className="text-3xl font-light uppercase tracking-widest mb-16 text-center italic">New Arrivals
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
          {products.map((product) => (
            <motion.div
              key={product.id}
              whileHover={{ y: -10 }}
              className="group relative cursor-pointer"
            >
              <div className="aspect-[4/5] overflow-hidden bg-neutral-900 mb-6">
                <img 
                  src={product.image} 
                  alt={product.name} 
                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                />
              
              <div className="flex justify-between items-start">
                
                  <h3 className="text-lg font-medium">{product.name}
                  <p className="text-sm text-gray-500 uppercase tracking-tighter">{product.category}
                
                <p className="font-mono">${product.price}
              
              <button className="mt-4 w-full py-2 border border-white/10 hover:border-white transition-colors flex items-center justify-center gap-2 text-xs uppercase tracking-widest">
                 Add to Cart
              
            </motion.div>
          ))}
        
      

      
      <footer className="py-20 border-t border-white/5 text-center">
        <p className="text-xs text-gray-600 uppercase tracking-[0.3em]">© 2026 SHOESY. Elevated Footwear.
      
    
  );
}