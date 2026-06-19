import { parseInlineFormatting } from '../utils/parseInlineFormatting';

const RichText = ({ text, className = '' }) => {
  const parts = parseInlineFormatting(text);

  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.type === 'bold' ? (
          <strong key={`bold-${index}`} className="font-semibold">
            {part.content}
          </strong>
        ) : (
          <span key={`text-${index}`}>{part.content}</span>
        ),
      )}
    </span>
  );
};

export default RichText;
