"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import type { Building, Section, Venue } from "./types";

export function useVenues(type?: string) {
  return useQuery({ queryKey: ["venues", type ?? "all"], queryFn: () => api<Venue[]>("/venues", { params: { type } }), staleTime: 600000 });
}

export function useBuildings() {
  return useQuery({ queryKey: ["buildings"], queryFn: () => api<Building[]>("/buildings"), staleTime: 600000 });
}

export function useSections() {
  return useQuery({ queryKey: ["sections"], queryFn: () => api<Section[]>("/sections"), staleTime: 600000 });
}

export function useNow() {
  return useQuery({ queryKey: ["demo-now"], queryFn: () => api<{ now: string }>("/demo/now"), refetchInterval: 15000 });
}

export interface ParkingLot {
  id: number;
  name: string;
  zone: string;
  cap_car: number;
  cap_bike: number;
  cap_bus: number;
  ev_bays: number;
  vip_bays: number;
  near_json: Record<string, number>;
}

export function useParkingLots() {
  return useQuery({ queryKey: ["parking-lots"], queryFn: () => api<ParkingLot[]>("/parking-lots"), staleTime: 600000 });
}

export interface GuestRoom {
  id: number;
  code: string;
  type: string;
  capacity: number;
  accessible: boolean;
  tariff_per_night: number;
}

export function useGuestRooms() {
  return useQuery({ queryKey: ["guest-rooms"], queryFn: () => api<GuestRoom[]>("/guest-rooms"), staleTime: 600000 });
}
