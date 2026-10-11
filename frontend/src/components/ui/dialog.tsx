import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
export function Modal({title,children,open,onClose}:{title:string,children:ReactNode,open:boolean,onClose:()=>void}){return <Dialog.Root open={open} onOpenChange={v=>!v&&onClose()}><Dialog.Portal><Dialog.Overlay className="modal-overlay"/><Dialog.Content className="modal-content" aria-describedby={undefined}><div className="modal-header"><Dialog.Title>{title}</Dialog.Title><Dialog.Close className="icon-button" aria-label="Fechar"><X size={20}/></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;}
