// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

jest.mock("framer-motion", () => {
  const React = require("react");

  const MockMotion = React.forwardRef((props, ref) => {
    const {
      children,
      animate,
      exit,
      initial,
      layout,
      transition,
      variants,
      whileHover,
      ...rest
    } = props;

    return React.createElement("div", { ref, ...rest }, children);
  });

  return {
    __esModule: true,
    AnimatePresence: ({ children }) =>
      React.createElement(React.Fragment, null, children),
    motion: new Proxy(
      {},
      {
        get: () => MockMotion,
      }
    ),
  };
});
