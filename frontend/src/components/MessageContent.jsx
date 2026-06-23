import DataTable from './DataTable';
import RichText from './RichText';
import { parseMessageBlocks } from '../utils/parseMessageContent';

const HEADING_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'];

const MessageContent = ({ text, isUser = false }) => {
  const blocks = parseMessageBlocks(text);
  const headingClass = isUser
    ? {
        1: 'text-xl font-extrabold text-white sm:text-2xl',
        2: 'text-lg font-bold text-white sm:text-xl',
        3: 'text-base font-bold text-white sm:text-lg',
        4: 'text-base font-bold text-white sm:text-lg',
        5: 'text-sm font-semibold text-white sm:text-[15px]',
        6: 'text-sm font-semibold text-white/95 sm:text-[15px]',
      }
    : {
        1: 'text-xl font-extrabold text-slate-900 sm:text-2xl',
        2: 'text-lg font-bold text-slate-900 sm:text-xl',
        3: 'text-base font-bold text-slate-900 sm:text-lg',
        4: 'text-base font-bold text-slate-900 sm:text-lg',
        5: 'text-sm font-semibold text-slate-800 sm:text-[15px]',
        6: 'text-sm font-semibold text-slate-800 sm:text-[15px]',
      };

  return (
    <div className={`space-y-3 break-words [overflow-wrap:anywhere] ${isUser ? 'text-white' : 'text-slate-700'}`}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const level = Math.min(Math.max(block.level, 1), 6);
          const Tag = HEADING_TAGS[level - 1];
          return (
            <Tag
              key={`heading-${index}`}
              className={`${headingClass[level]} mt-4 leading-tight tracking-tight first:mt-0`}
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
