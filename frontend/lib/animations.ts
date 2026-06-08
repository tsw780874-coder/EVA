export const fadeInUp = {
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true } as const,
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }
};

export const fadeInUpDelayed = (delay: number) => ({
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true } as const,
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number], delay }
});
