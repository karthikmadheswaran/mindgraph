import { useEffect, useState } from "react";
import { motion } from "framer-motion";

const pageVariants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 30,
    },
  },
};

export default function AnimatedView({ children, viewKey, isActive }) {
  const [hasBeenActive, setHasBeenActive] = useState(isActive);

  useEffect(() => {
    if (isActive && !hasBeenActive) {
      setHasBeenActive(true);
    }
  }, [isActive, hasBeenActive]);

  return (
    <motion.div
      data-view={viewKey}
      initial="initial"
      animate={hasBeenActive ? "animate" : "initial"}
      variants={pageVariants}
    >
      {children}
    </motion.div>
  );
}
