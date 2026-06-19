import DataTable from './DataTable';
import RichText from './RichText';
import { parseMessageBlocks } from '../utils/parseMessageContent';

const MessageContent = ({ text, isUser = false }) => {
  const blocks = parseMessageBlocks(text);
  const headingClass = isUser
    ? {
        1: 'text-base font-bold text-white sm:text-lg',
        2: 'text-sm font-bold text-white sm:text-base',
        3: 'text-sm font-semibold text-white sm:text-[15px]',
      }
    : {
        1: 'text-base font-bold text-slate-900 sm:text-lg',
        2: 'text-sm font-bold text-slate-900 sm:text-base',
        3: 'text-sm font-semibold text-slate-800 sm:text-[15px]',
      };

  return (
    <div className={`space-y-3 break-words [overflow-wrap:anywhere] ${isUser ? 'text-white' : 'text-slate-700'}`}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Tag = block.level === 1 ? 'h1' : block.level === 2 ? 'h2' : 'h3';
          return (
            <Tag
              key={`heading-${index}`}
              className={`${headingClass[block.level] || headingClass[3]} leading-snug`}
            >
              <RichText text={block.content} />
            </Tag>
          );
        }

        if (block.type === 'table') {
          return (
            <DataTable
              key={`table-${index}`}
              headers={block.headers}
              rows={block.rows}
            />
          );
        }

        if (block.type === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul';
          const listClass = block.ordered ? 'chat-list-decimal' : 'chat-list-disc';
          return (
            <ListTag key={`list-${index}`} className={listClass}>
              {block.items.map((item, itemIndex) => (
                <li key={`${itemIndex}-${item.slice(0, 24)}`}>
                  <RichText text={item} />
                </li>
              ))}
            </ListTag>
          );
        }

        return (
          <p key={`text-${index}`} className="whitespace-pre-wrap text-sm leading-relaxed sm:text-[15px]">
            <RichText text={block.content} />
          </p>
        );
      })}
    </div>
  );
};

export default MessageContent;
